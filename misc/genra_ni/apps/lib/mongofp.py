import numpy as np
import pandas as pd
import copy
import pymongo
import sys
import re

def searchCollByFP(cid,s0=0.5,col='chm_fp',fpn='mrgn',
                   CID=None,
                   i1=0,i2=None,dbg=False,DB=None,
                   max_hits=100):
    Q0 = DB[col].find_one({'dsstox_cid':cid})
    if not Q0: return
    C = DB.compound.find_one({'dsstox_cid':Q0['dsstox_cid']})
    Q = Q0[fpn]
    qmin= int(s0*Q['n'])
    qmax= int(Q['n']/s0)
    if dbg: print '>Query: {} {} {}'.format(C['name'],C['dsstox_cid'],C['smiles'])

    Match1 = {'%s.n'%fpn:{'$gte':qmin, '$lte':qmax},
                    '%s.ds'%fpn:{'$in':Q['ds']}
              }
    if CID: Match1['dsstox_cid']={'$in':CID}

    Agg = [
        {'$match': Match1},
        {'$project': 
             {'jaccard': 
                 {'$let':
                  {'vars': 
                   {'olap': {'$size':{'$setIntersection': ['$%s.ds'%fpn,Q['ds']] }}},
                   'in': {'$divide':['$$olap',
                                     {'$subtract': [{'$add':[Q['n'],'$%s.n'%fpn]},'$$olap'] }]}
                  }
                 },
              '_id':0,
              'dsstox_cid':1,
              'dsstox_sid':1,
              'mol_weight':1,
              'name':1,
             }
        },
        {'$match':{'jaccard':{'$gte':s0}}},
        {'$sort': {'jaccard':-1}},
        {'$limit': max_hits}
    ]

    #print qmin,qmax
    return list(DB[col].aggregate(Agg))


def searchFP(cid,fp='chm_mrgn',DB=None,sel_by=None,**kwargs):
    """
    cid: dsstox_cid
    fp: is the fingerprint name that matches COL
    sel_by:  Find similar chemicals that also have data in another data collection. 
             e.g. If sel_by is tox_txrf then search results are limited to the chemicals 
             with toxicity data 
    """
    COL = dict(chm_mrgn='chm_fp',chm_httr='chm_fp',chm_ct='chemotypes',
               bio_txct='bio_fp',bio_tx21='tox21_fp',
               tox_txrf='tox5_fp')

    DS  = dict(chm_mrgn='mrgn',chm_httr='httr',chm_ct='chemotypes',
               bio_txct='bio1',bio_tx21='t211',
               tox_txrf='tox_fpp1')

    col=COL.get(fp)
    ds =DS.get(fp)    
    if not (ds and col): return

    CID_h= None
    if sel_by and COL.has_key(sel_by):
        col_sel =COL.get(sel_by)    
        CID_h = DB[col_sel].find({'dsstox_cid':{'$exists':1}}).distinct('dsstox_cid')
        if cid not in CID_h: CID_h.append(cid)

    # Find NN
    H  = searchCollByFP(cid=cid,col=col,fpn=ds,DB=DB,CID=CID_h,**kwargs)
    if not H: H=[] 
    
    Q = [i for i in H if i['dsstox_cid']==cid]
    H1= sorted([i for i in H if i['dsstox_cid']!=cid],key=lambda x: x['jaccard'],reverse=True)
    
    return Q+H1

def getFP(CID,fp='chm_mrgn',FP=None,DB=None,fill=None):
    COL = dict(chm_mrgn='chm_fp',chm_httr='chm_fp',chm_ct='chm_fp',
               bio_txct='bio_fp',bio_tx21='tox21_fp',
               tox_txrf='tox_fp',toxp_txrf='tox5_fp',toxn_txrf='tox5_fp',)

    DS  = dict(chm_mrgn='mrgn',chm_httr='httr',chm_ct='chmtp2',
               bio_txct='bio1',bio_tx21='t211',toxp_txrf='tox_fpp1',toxn_txrf='tox_fpn1',
               tox_txrf='tox1')

    col=COL.get(fp)
    ds =DS.get(fp)    
    if not (ds and col): return

    Agg = [
            # Match chemicals in cluster
            {'$match': {
                     'dsstox_cid':{'$in':CID}}
            },
            # Include these fields
            {'$project':{'dsstox_cid':1,'name':1,'_id':0,
                        'fp':'$%s.ds'%ds},
            },
            # Unwind the fp 
            {'$unwind':"$fp"}
            ]
    if FP: Agg.append({'$match': {'fp':{'$in': FP}}})
    
    X = DB[col].aggregate(Agg,allowDiskUse=True)
    if not X: return
    try:
        R = pd.DataFrame(X['result'])
    except:
        R = pd.DataFrame(list(X))

    if R.shape[0]==0 or R.shape[1]==0: return pd.DataFrame()

    return pd.pivot_table(R,index=['dsstox_cid'],columns='fp',values='name',aggfunc=len,fill_value=fill)

def getFPHelp(DB,labels):
    TT_DF = pd.DataFrame(list(DB.fp_stats.find({'ds': {'$in': labels}}, {'ds': 1, 'name': 1, 'notes': 1, '_id': 0})))
    if TT_DF.empty is False:
        TT_DF=TT_DF.set_index('ds')
    TT_DF.replace(dict(name={np.nan: None}, notes={np.nan: None})) #Workaround since can't fillna with None
    return TT_DF

def getChemBioSummary(CID,col=None,ds=None,fill=None,cls='fp'):
    if not cls: cls='fp'
    Agg = [
            # Match chemicals in cluster
            {'$match': {
                     'dsstox_cid':{'$in':CID}}
            },
            # Include these fields
            {'$project':{'dsstox_cid':1,'_id':0,
                        cls:'$'+ds},
            },
            {'$unwind':'$'+cls}

            ]
   
    X = col.aggregate(Agg,allowDiskUse=True)
    if not X: return
    try:
        R = X['result']
    except:
        R = list(X)

    return R

def getChemToxSummary(CID,col=None):
    Agg = [
            # Match chemicals in cluster
            {'$match': {
                     'dsstox_cid':{'$in':CID}}
            },
            # Include these fields
            {'$project':{'dsstox_cid':1,'_id':0,
                        'tox_fp':{'$concatArrays':['$tox_fpp1.ds','$tox_fpn1.ds']}},
            },
            {'$unwind':'$tox_fp'}

            ]

    X = col.aggregate(Agg,allowDiskUse=True)
    if not X: return
    try:
        R = X['result']
    except:
        R = list(X)

    return R

def getChemPhysSummary(nn_cids,DB):

    #target_phys = list(col.find({'dsstox_cid':target_cid},{'_id':0,'phys_vals':1}))
    X = DB['test_fp'].find({'dsstox_cid':{'$in':nn_cids}},{'_id':0,'dsstox_cid':1,'phys':1})
    R = list(X)
    return R

def getChemSummary(CID,MDB=None,Colls=None):
    Agg_match= {'$match': {'dsstox_cid':{'$in':CID}}}
    Agg_proj = {'$project':{'dsstox_cid':1,'_id':0,'n':''}}
    
    Res = []
    for prop,db_coll in Colls.iteritems():
        Agg_proj['$project']['n'] = db_coll['projn']
        Agg = [Agg_match,Agg_proj]
        X = MDB[db_coll['coll']].aggregate(Agg,allowDiskUse=True)
        
        if not X: continue
        R = None
        try:
            R = X['result']
        except:
            R = list(X)
        
        R_df = pd.DataFrame(R)
        R_df['prop']=prop
        Res.append(R_df)
        
    X = pd.concat(Res)
    R = X.pivot_table(index='dsstox_cid',columns='prop',values='n',aggfunc=min)
    R.fillna(0,inplace=True)

    return R



def getChemToxCastNNSummary(cid,s0=0.01,k0=10,fp='chm_mrgn',MDB=None,col='bio_fp',ds='bio1',
                            sel_by=None,                            
                            dbg=False):
    
    Hits  = searchFP(cid,fp=fp,s0=s0,max_hits=k0,DB=MDB,sel_by=sel_by)
    if not Hits:
        return
    
    NN      = pd.DataFrame(Hits)
    k0      = NN.shape[0]

    CID = list(NN.dsstox_cid)

    AI1 = None
    R1  = None

    # get bioactivity data for NN
    B1 = pd.DataFrame(getChemBioSummary(CID,col=MDB[col],ds='%s.ds'%ds,cls='bio_fp'))

    R1 = B1.merge(NN,left_on='dsstox_cid',right_on='dsstox_cid')

    return R1

def getChemTox21NNSummary(cid,s0=0.01,k0=10,fp='chm_mrgn',MDB=None,col='tx21_fp',ds='t211',
                          sel_by=None,                            
                          dbg=False):
    
    Hits  = searchFP(cid,fp=fp,s0=s0,max_hits=k0,DB=MDB,sel_by=sel_by)
    if not Hits:
        return
    
    NN      = pd.DataFrame(Hits)
    k0      = NN.shape[0]

    CID = list(NN.dsstox_cid)

    AI1 = None
    R1  = None

    # Get assay information
    AI1= pd.DataFrame(list(MDB.bio_fp_info.find({'target_family':{'$regex':'^((?!background).)'}},dict(_id=0))))
    AI1.fillna('',inplace=True)

    # get bioactivity data for NN
    B1 = pd.DataFrame(getChemBioSummary(CID,col=MDB[col],ds='%s.ds'%ds,cls='bio_fp'))
    B1['bio_fp']=B1.bio_fp.str.lower()
    AI1['bio_fp']=AI1.bio_fp.str.lower()

    R1 = B1.merge(AI1,left_on='bio_fp',right_on='bio_fp').merge(NN,left_on='dsstox_cid',right_on='dsstox_cid')

    return R1

def getChemToxRefNNSummary(cid,s0=0.01,k0=10,fp='chm_mrgn',col='tox5_fp',ds='tox_fpp1',MDB=None,
                           sel_by=None,                            
                           dbg=False):

    Hits  = searchFP(cid,fp=fp,s0=s0,max_hits=k0,DB=MDB,sel_by=sel_by)
    if not Hits:
        return pd.DataFrame()
    
    NN      = pd.DataFrame(Hits)
    k0      = NN.shape[0]

    CID = list(NN.dsstox_cid)
    
    T1 = pd.DataFrame(getChemToxSummary(CID,col=MDB[col]))
    if T1.shape[0]==0: return pd.DataFrame() 
    T1['study']=T1.tox_fp.apply(lambda x: x.split(':')[0])
    T1['organ']=T1.tox_fp.apply(lambda x: x.split(':')[1].lower())
    R1=T1.merge(NN,left_on='dsstox_cid',right_on='dsstox_cid')
    
    return R1


def getChemPhysChemNNSummary(cid, s0=.01, k0=10, fp='chm_mrgn', MDB=None, DDB=None, sel_by=None):
    Hits = searchFP(cid, fp=fp, s0=s0, max_hits=k0, DB=MDB, sel_by=sel_by)
    if not Hits:
        return pd.DataFrame()

    NN = pd.DataFrame(Hits)
    k0 = NN.shape[0]
    CID = list(NN.dsstox_cid)

    T0 = pd.DataFrame(getChemPhysSummary(CID, DB=DDB))
    T1 = T0.join(pd.DataFrame(T0['phys'].to_dict()).T)
    del T1['phys']
    R1 = T1.merge(NN, left_on='dsstox_cid', right_on='dsstox_cid')
    del R1['dsstox_cid']
    return R1


def getChemToxRefNNInfo(cid,s0=0.01,k0=10,fp='chm_mrgn',
                        MDB=None,col='tox5_fp',ds_pos='tox_fpp1',ds_neg='tox_fpn1',
                        
                        dbg=False):
    
    Hits  = searchFP(cid,fp=fp,s0=s0,max_hits=k0,DB=MDB)
    if not Hits:
        return pd.DataFrame()
    
    NN      = pd.DataFrame(Hits)
    k0      = NN.shape[0]

    CID = list(NN.dsstox_cid)
    
    T1 = pd.DataFrame(getChemToxSummary(CID,col=MDB[col]))
    if T1.shape[0]==0: return pd.DataFrame() 
    T1['study']=T1.tox_fp.apply(lambda x: x.split(':')[0])
    T1['organ']=T1.tox_fp.apply(lambda x: x.split(':')[1].lower())
    R1=T1.merge(NN,left_on='dsstox_cid',right_on='dsstox_cid')
    
    return R1

def getChemToxRefNNData(cid,s0=0.01,k0=10,fp='chm_mrgn',tox=None,pos_min=0,neg_min=0,
                        MDB=None,col='tox5_fp',ds_pos='tox_fpp1',ds_neg='tox_fpn1',   
                        sel_by=None,                            
                        filt_by=None,
                        dbg=False):
    target_cid = cid
    # Get NN
    Hits  = searchFP(cid,fp=fp,s0=s0,max_hits=k0,DB=MDB,sel_by=sel_by)
    if not Hits:
        return pd.DataFrame()

    NN      = pd.DataFrame(Hits)
    k0      = NN.shape[0]
    NN['d'] = 1-NN.jaccard
    CID = list(NN.dsstox_cid)

    # Load Tox Data including doses
    TX_pos = []
    TX_neg = []
    for X in MDB[col].find({'dsstox_cid':{'$in':CID}},dict(_id=0,dsstox_cid=1,name=1,tox_q1=1,tox_fpn1=1)):
        cid = X.get('dsstox_cid')
        if not cid: continue
        name= X['name']
        for x in X['tox_q1']:
            x['name']=name
            x['dsstox_cid']=cid

        TX_pos += X['tox_q1']
        Y = []
        for y in X['tox_fpn1']['ds']:
            Y.append(dict(dsstox_cid=cid,name=name,neg=1,effect=y))
        TX_neg += Y

    if len(TX_pos)==0 or len(TX_neg)==0: return

    # Prepare the data for pivot
    TX_pos = pd.DataFrame(TX_pos)
    TX_pos['dose_w_unit'] = TX_pos.apply(lambda x: "%(dose)10.3f %(dose_unit)s" % dict(x),axis=1)
    TX_neg = pd.DataFrame(TX_neg)
    # Pivot the positives and negatives from Tox
    Neg=TX_neg.pivot_table(index='dsstox_cid',columns='effect',values='neg',aggfunc=min)

    Pos_values = {cid: {} for cid in list(TX_pos['dsstox_cid'].unique())}
    Pos_units = {cid: {} for cid in list(TX_pos['dsstox_cid'].unique())}
    for index, group in TX_pos.groupby(['dsstox_cid', 'effect']):
        cid, effect = index
        min_dose_index = group['dose'].idxmin()
        min_dose, min_unit = group.loc[min_dose_index][['dose', 'dose_unit']].values
        Pos_values[cid][effect] = min_dose
        Pos_units[cid][effect] = min_unit

    Pos = pd.DataFrame(Pos_values).T
    Pos.index.name = 'dsstox_cid'

    # Fill the values for the common tox effects
    J=Pos.columns.intersection(Neg.columns)
    PJ=Pos.columns.difference(Neg.columns)
    NJ=Neg.columns.difference(Pos.columns)

    # Combine the common endpoints first
    P1 = Pos[J]
    N1 = Neg[J]

    # Remaining Positive
    P2 = Pos[PJ]
    N2 = Neg[NJ]

    # Label negatives
    N2 = N2.where(N2!=1,'no_effect')
    P1 = P1.where(N1!=1,'no_effect')
    TX = pd.merge(P1,P2,left_index=True,right_index=True)
    TX = TX.merge(N2,left_index=True,right_index=True)

    # Merge with NN data
    TX = TX.reset_index()
    TX = TX.merge(NN,left_on='dsstox_cid',right_on='dsstox_cid',how='outer').set_index(list(NN.columns))
    # Filter out columns based on filt_by
    if filt_by!=None and len(filt_by)>1:
        I1 = TX.columns.str.contains(filt_by,case=False)
        if np.sum(I1)==0: return
        TX = TX[TX.columns[I1]]

    if TX.shape[1]==0: return

    # Skip all chemicals without any data but keep the target
    TX['tox_n']=TX.notnull().sum(axis=1)
    TX = TX.query("tox_n>0 or jaccard==1").drop('tox_n',axis=1)
    TX.sort_index('index','jaccard',ascending=False,inplace=True)
    TX=TX.where(TX.notnull(),other='no_data')
    TX['cls']=['target']+['analog']*(TX.shape[0]-1)
    ind = list(TX.index.names)+['cls']
    TX = TX.reset_index().set_index(ind)

    # Summarise row labels
    RL = pd.DataFrame([dict(zip(TX.index.names,x)) for x in TX.index.values])
    RL.rename(columns=dict(name='label'),inplace=True)
    RL['svg_url']= RL.dsstox_cid.apply(lambda x: "/api/genra/v3/viewChemGlyph/%s.svg" % x)

    # Summarize column labels
    # count the number of chemicals with dose, no effect and no data
    print(TX.head())
    TX2 = TX.copy()
    TX2[(TX2 != 'no_data') & (TX2 != 'no_effect')] = 'dose'
    CL = pd.DataFrame(TX2.apply(pd.value_counts).T.to_dict('records'),dtype=np.int)
    CL.fillna(0,inplace=True)
    # Change the counts to integer
    for c in CL: CL[c] = CL[c].astype(np.int)
    CL['label']=TX2.columns
    CL['study']=CL.label.apply(lambda x: x.split(':')[0])
    CL['organ']=CL.label.apply(lambda x: x.split(':')[1])

    #Tooltips
    # TT_DF=getFPHelp(MDB,CL['label'].tolist())
    # TT_DF.index=TT_DF.index.str.lower()
    # CL['lower_label']=CL['label'].str.lower()
    # CL=CL.join(TT_DF,on='lower_label')
    # del CL['lower_label']
    # # If negative and positive mins are defined then filter by them
    # q = None
    # if pos_min>0 or neg_min>0:
    #     q = "dose>=%d" % pos_min
    #     q += "and no_effect>=%d" % pos_min
    #     CL = CL.query(q)
    #     TX = TX[CL.label]

    # Rows
    RD = TX.reset_index(drop=True)
    print(RD)
    RD.index = RL.dsstox_cid

    return dict(RL=CL,CL=RL,D=TX,
                cols=RD.to_dict('index'),
                row_labs=CL.to_dict('records'),
                col_labs=RL.to_dict('records'),
                units=Pos_units,
                nn_opts=dict(target=target_cid,s0=s0,k0=k0,fp=fp))



