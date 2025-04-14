import sklearn.metrics as metrics
from scipy.spatial.distance import squareform,pdist
from mongofp import *


def getKNN(cid,Sim,k0=10,s0=0,sim=False,drop_self=True):
    S_i = Sim.ix[cid,:]
    if drop_self:
        S_i = S_i.drop(cid)
    NN  = None
    
    if k0 and s0:
        S_i = S_i[S_i>s0]
        S_i.sort_values()
        NN = S_i[-k0:]
    elif k0:
        S_i.sort_values()
        NN = S_i[-k0:]
    elif s0:
        NN = S_i[S_i>s0]
    
    if sim:
        return NN
    else:
        return NN.index

def permuteAUC(auc0,Act,N=100,pos=1):
    Y_t,Y_p = Act.a_t,Act.a_p
    AUC = []
    for i in range(N):
        Y_r = np.array(Y_t.copy())
        np.random.shuffle(Y_r)
        fpr,tpr,t0 = metrics.roc_curve(Y_r,Y_p,pos_label=pos)
        AUC.append(metrics.auc(fpr,tpr))

    p_val = 1.0*np.sum(np.array(AUC)>auc0)/N

    return p_val
    
def calcAUC(Act,N=100,pos=1):
    #t0,auc,p_val=0.5,0,1
    fpr,tpr,t0 = metrics.roc_curve(Act.a_t,Act.a_p,pos_label=1,drop_intermediate=False)
    if np.isnan(fpr).any(): fpr = np.array([0])
    if np.isnan(tpr).any(): tpr = np.array([1])
    tnr = 1-fpr
    Roc = pd.DataFrame(zip(fpr,tnr,tpr,t0),columns=['fpr','sp','sn','t0'])
    Roc['BA']=0.5*(Roc.sp+Roc.sn)
    
    try:
        auc = metrics.auc(fpr,tpr)
        p_val=permuteAUC(auc,Act,N,pos)
        Roc0 = Roc.query("t0<=1")
        i0 = Roc0.sort_values(by='BA',ascending=False).index[0]
        t0=Roc0.t0.ix[i0]
    except:
        t0,auc,p_val=0.5,0,1
        
    return t0,auc,p_val,Roc       


def calcSimWtAct(A,S,k0=5,s0=0.0):
    A = A[pd.notnull(A)]
    CID = A.index
    S1= S.ix[CID,CID]
    
    Res=pd.DataFrame(np.zeros((len(CID),4)),index=CID,
                     columns=['a_t','a_p','n_p','n_n'])
    
    for cid in CID:
        S_i  = getKNN(cid,S1,k0=k0,s0=s0,sim=True)
        A_i  = A[S_i.index]
        Res.ix[cid,'a_t']=A.ix[cid] 
        Res.ix[cid,'a_p']=0 if S_i.sum()==0 else np.sum(A_i*S_i)/S_i.sum()
        Res.ix[cid,'n_p']=(A_i>0).sum()
        Res.ix[cid,'n_n']=(A_i==0).sum()

    return Res
    
def predSimWtAct(cid,A,S,p,k0=5,s0=0.0,t0=0.5):
    a_t = A.ix[cid] if cid in A.index else None
    A = A[pd.notnull(A)]
    CID = list(A.index)
    if cid not in CID: CID = [cid] + CID
    S1= S.ix[CID,CID]
    
    S_i  = getKNN(cid,S1,k0=k0,s0=s0,sim=True)
    A_i  = A[S_i.index]

    if p>0.2:
        t0 = 0.5
        
    a_s=a_p  = 0
    if S_i.sum()==0:
        a_s = 0
        a_p = 0
    else:
        a_s = np.sum(A_i*S_i)/S_i.sum()
        a_p = 1 if a_s>=t0 else 0

    
    if a_t > 0:
        if a_p == 1:
            pred='TP'
        elif a_p == 0:
            pred='FN'
    elif a_t==0:
        if a_p == 1:
            pred='FP'
        elif a_p == 0:
            pred='TN'
    else:
        if a_p == 1:
            pred='Pos'
        elif a_p == 0:
            pred='Neg'

    a_s = np.round(a_s,decimals=3)
    return dict(pred=pred,a_t=a_t,a_s=a_s,a_p=a_p)
        

def runGenRA(cid,Y=None,CID=None,DB=None,
             fp_x='chm_mrgn',fp_y='toxp_txrf',
             sel_by=None,
             k0=10,s0=0.1,
             metric='jaccard',
             pred=True,
             ret = None,
             wt=True,n_perm=100):

    """
    cid  : the DSSTOX CID of the target chemical (required)

    Y    : list of toxicities for evaluation of activities (optional)

    CID  : list of dsstox_cids of chemicals to consider in neighbourhood (optional)

    DB   : reference to mongodb (required)

    fp_x : fingerprint for chemical similarity. Options:
          - chm_mrgn: RDKit Morgan (default)
          - chm_httr: RDKit Torsion
          - chm_ct  : ChemoTypes 

    fp_y: fingerprint for predicted bioactivity. This is resolved to a specific 
          database collection and attribute. Currently only consider toxicity. Options
          - toxp_txrf: toxref toxicity classifications. 

    sel_by: when finding nearest neighbours of target, select the neighbours based on 
            availability of this information. Options:
          - tox_txrf: toxref toxicity classifications. 

    k0    : Number of nearest neighbours to consider

    s0    : Similarity threshold measured by metric

    metric: Similarity metric. Options:
          - Jaccard (default)
    
    n_perm: Number of permutations for testing significance of AUC

    pred  : Whether to predict activity for target or just calculate the 
            predictive performances

    ret   : Results to return. Options:
          - full: a list with three elements 
            1. Predictions for target
            2. Performance results for neighbourhood
            3. Similarity scores for chemicals in neighbourhood
          - else:
            * Performance results

    Description of returned values:
    
    * Predictions for target - a list of predictions, one for each bioactivity outcome. 
      Each prediction is a dict with the following keys:
      - dsstox_cid  : DSSTOX CID of target
      - out         : bioactivity/toxicity endpoint
      - k0          : k0
      - s0          : s0
      - fp          : fp_x
      - a_t         : Observed activity of target for out 
      - a_s         : Similarity weighted bioactivity of target across neighbours
      - a_p         : Predicted activity 0/1 based on threshold t0
      - auc         : ROC area under curve across a_s and a_t for neighbours
      - t0          : activity threshold that produces best balanced accuracy
      - p_val       : the significance of auc across n_perm
      - pred        : the prediction class 
                      if a_t known  : one of TN/TP/FN/FP
                      if a_t unknown: one of Pos/Neg

    * Performance results for neighbourhood as a dict in which keys are 
      bioactivity/toxicity endpoints and values are dictionaries with the following
      keys:
      - out        : Binary activity of each analog (no effect:0/effect: 1)
      - act        : Similarity weighted activities for each analog in the 
                     neighbourhood as a pandas.DataFrame with the following columns:
             - dsstox_cid: DSSTOX CID of analog (index)
             - a_t       : True activity of analog
             - a_p       : Simiarity weighted bioactivity of analog
             - n_p       : Number of positives
             - n_n       : Number of negatives 
      - roc        : The receiver operating characteristic for the neighbourhood 
                     as a dataframe with the following columns:
             - fpr       : false positive rate
             - sp        : specificity
             - sn        : sensitivity
             - t0        : score threshold
             - BA        : balanced accuracy = 0.5 * (sn+sp)

    * Similarity matrix for all k0 chemicals considered in neighbourhood as a 
      k0xk0 pandas.DataFrame in which rows and columns are indexed by dsstox_cid and
      the value of each cell is the similarity score based on above metric
      
    """

    Hits = searchFP(cid,fp=fp_x,s0=s0,max_hits=k0,DB=DB,sel_by=sel_by)
   
    if not Hits: 
        Hits=[] 
        return Hits
        #return jsonify(dict(hits=[]))

    NN  = pd.DataFrame(Hits)
    CID0 = list(set(NN.dsstox_cid).intersection(CID)) if CID else list(NN.dsstox_cid)
    # Get fingerprints
    X_fp = getFP(CID0,DB=DB,fill=0,fp=fp_x)
    if fp_y=='toxp_txrf':
        Y_pos = getFP(CID0,DB=DB,fp=fp_y,FP=Y) 
        Y_neg = getFP(CID0,DB=DB,fp='toxn_txrf',FP=Y)
        endpoints=list(set(Y_pos.columns.values)|set(Y_neg.columns.values))
        endpoints.sort()
        Y_fp=Y_pos.reindex_axis(endpoints,axis=1)
        Y_fp = Y_fp.reindex_axis(CID0, axis=0)
        Y_fp[Y_neg==1]=0
    else:
        Y_fp = getFP(CID0,DB=DB,fp=fp_y,FP=Y,fill=0)
    # Calc distance
    S = 1-pd.DataFrame(squareform(pdist(X_fp,metric)),
                       columns=X_fp.index,index=X_fp.index)
    
    
    Res,R,Perf = [],{},{}

    for y in Y_fp.columns:
        #print ">",y
        Act = calcSimWtAct(Y_fp[y],S,k0=k0,s0=s0)
        t0,auc,p_val,Roc= calcAUC(Act,N=n_perm)
        Yi = Y_fp[y]
        Yi = Yi[Yi.notnull()]
        R = {'out':y,'auc':auc,'k0':k0,'s0':s0,'fp':fp_x,
             'n_pos':(Yi==1).sum(),'n_neg':(Yi==0).sum(),
             'p_val':p_val,'t0':t0,'dsstox_cid':cid}

        Perf[y]=dict(roc=Roc,act=Act,out=Yi)

        if pred:
            R.update(predSimWtAct(cid,Yi,S,p_val,k0=k0,s0=s0,t0=t0))

        Res.append(R)

    if ret == 'all':
        return Res,Perf,S
    else:
        return Res
    
 
