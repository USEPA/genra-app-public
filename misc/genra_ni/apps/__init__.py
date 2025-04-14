from __future__ import print_function

from flask import Flask, jsonify, request, render_template, abort, make_response,url_for, json
from bson import json_util
import pymongo
import re,math
import pandas as pd
import numpy as np
from flasgger import Swagger
import os,sys,re
from itertools import product
import matplotlib.cm as cm
from subprocess import call

# Set up the local source files
# Prod:
# sys.path.insert(0,'/var/www/GenRA_App')
# Devel:
DIR = os.getcwd()
sys.path.append(DIR)

from lib.mongofp import *
from lib.misc import *
from lib.vis import *
from lib.genrapred import *

MAX_HITS = 100


# Prod:
# con = pymongo.MongoClient("enter correct local URI, DB genra_v3")
# Devel:
# con = pymongo.MongoClient("enter correct URI for PB_V4")
con = pymongo.MongoClient("enter correct URI for PB_V1")

# DB = con['genra_dev_v4']
DB = con['genradb_v1']

NO_SVG = """<?xml version="1.0" encoding="iso-8859-1"?>
<svg:svg version="1.1" baseProfile="full"
        xmlns:svg="http://www.w3.org/2000/svg"
        xmlns:xlink="http://www.w3.org/1999/xlink"
        xml:space="preserve" width="100px" height="100px" >
<svg:polygon fill="rgb(255,255,255)" stroke="none" stroke-width="0" points="0.00,0.00 100.00,0.00 100.00,100.00 0.00,100.00 0.00,0.00"></svg:polygon>
</svg:svg>"""

app = Flask(__name__)
Swagger(app)

@app.errorhandler(404)
def notFound(error):
    return jsonify( { 'error': 'Notfound' } )

# @app.route('/app/genra/v3')
# def runAppV3():
#     return app.send_static_file("app3.html")

@app.route('/genra')
def runAppV3():
    return app.send_static_file("app4.html")

@app.route('/api/genra/v3/searchChemNames/', methods=['GET'])
def searchChemNames():
    x  = request.args.get('name')
    name = "^%s" % x
    X = [i['name'] for i in
         DB.compound.find({'name': {'$regex':name,'$options':'i'}},
                          {'_id':0,'name':1}).limit(MAX_HITS)]

    X += [i['syn'] for i in
          DB.compound.find({'syn':
                            {'$elemMatch':{'$regex':name,'$options':'i'}}},
                           {'_id':0,'syn.$':1}).limit(MAX_HITS)]

    return jsonify(dict(result=flatten(X)))

@app.route('/api/genra/v3/searchChems/', methods=['GET'])
def searchChems():
    """
    Search chemicals
    Specify one of: name, casrn, smiles, cid
    ---
    tags:
      - searchChems
    parameters:
      - name: txt
        in: query
        type: string
        description: a partial pattern containing chemical name, casrn, synonym, dtx id
    responses:
      200:
        description: A list of chemical hits
        schema:
           columns:
              type: array
              description: The list of attributes for each chemical
              items:
                type: string
           data:
              type: array
              description: The list of chemicals that matched the query
              items:
                type: object
                properties:
                  casrn:
                      type: string
                      description: CASRN of chemical
                  dsstox_cid:
                      type: string
                      description: DSSTOX CID of chemical
                  name:
                      type: string
                      description: Name of chemical
    """

    txt = str(request.args.get('txt'))

    ret   = dict(_id=0,name=1,casrn=1,dsstox_cid=1)

    Q = {}
    Q['$or']=[{'name':{'$regex':txt,'$options':'i'}},
              {'syn': {'$regex':txt,'$options':'i'}},
              {'casrn':{'$regex':txt,'$options':'i'}},
              {'dsstox_cid':txt}
              ]

    R = list(DB.compound.find(Q,ret).limit(MAX_HITS))

    return jsonify(dict(hits=R))


@app.route('/api/genra/v3/getChem/', methods=['GET'])
def getChem():
    """
    Get chemical
    input: dsstox_cid
    ---
    tags:
      - getChem
    parameters:
      - name: dsstox_cid
        in: query
        type: string
        description: a partial string containing the chemical DSSTOX CID
    responses:
      200:
        description: A list of chemical hits
        schema:
           columns:
              type: array
              description: The list of attributes for each chemical
              items:
                type: string
           data:
              type: array
              description: The list of chemicals that matched the query
              items:
                type: object
                properties:
                  casrn:
                      type: string
                      description: CASRN of chemical
                  dsstox_cid:
                      type: string
                      description: DSSTOX CID of chemical
                  name:
                      type: string
                      description: Name of chemical
    """
    cid   = request.args.get('dsstox_cid')
    ret   = dict(_id=0,viz=0)

    Q= dict(dsstox_cid=cid)

    R = DB.compound.find_one(Q,ret)
    R = {k:v for k,v in R.iteritems() if v==v}
    return jsonify(dict(chem=R))
    #return jsonify(dict(results=dict(hits=R)))

@app.route('/api/genra/v3/getChemF/', methods=['GET'])
def getChemF():
    """
    Get chemical with url links to external sites
    input: dsstox_cid
    ---
    tags:
      - getChemF
    parameters:
      - name: dsstox_cid
        in: query
        type: string
        description: a partial string containing the chemical DSSTOX CID
    responses:
      200:
        description: A list of chemical hits
        schema:
           columns:
              type: array
              description: The list of attributes for each chemical
              items:
                type: string
           data:
              type: array
              description: The list of chemicals that matched the query
              items:
                type: object
                properties:
                  casrn:
                      type: string
                      description: CASRN of chemical
                  dsstox_cid:
                      type: string
                      description: DSSTOX CID of chemical
                  name:
                      type: string
                      description: Name of chemical
    """
    cid   = request.args.get('dsstox_cid')
    ret   = dict(_id=0,viz=0,tag=0)

    k2lab = dict(name         ="name",
                 casrn        ="casrn",
                 dsstox_cid   ="dsstox_cid",
                 chemspider_id="ChemSpider",
                 dsstox_sid   ="DSSTox",
                 iupac        ="IUPAC",
                 pubchem_cid  ="PubChem",
                 mol_weight   ="MW",
                 smiles       ="SMILES")


    Q= dict(dsstox_cid=cid)

    R = DB.compound.find_one(Q,ret)
    R = {k2lab.get(k):v for k,v in R.iteritems() if v==v and k in k2lab.keys()}
    if R.has_key('MW'):
        R['MW']=np.round(R['MW'],decimals=3)
    return jsonify(dict(chem=R))
    #return jsonify(dict(results=dict(hits=R)))

@app.route('/api/genra/v3/getChemNN/', methods=['GET'])
def getChemNN():
    """
    Get nearest neighbours for chemical based on chm, bio or tox descriptors
    Specify one of: casrn or dsstox_cid
    ---
    tags:
      - getChemNN
    parameters:
      - name: dsstox_cid
        in: query
        type: string
        default: null
        required: true
        paramType: query
        description: the DSSTOX CID of the input chemical
      - name: k0
        in: query
        type: int
        paramType: query
        description: The number of nearest neighbours to return
        defaultValue: 12
      - name: s0
        in: query
        type: float
        paramType: query
        description: The Jaccard similarity threshold
        defaultValue: 0.1
      - name: fp
        in: query
        type: string
        paramType: query
        enum:
          - chm_mrgn
          - chm_httr
          - chm_ct
          - bio_txct
          - bio_tx21
          - tox_txrf
        description: the type of fingerprint to use for similarity searching
    responses:
      200:
        description: A list of chemical hits
    """

    cid   = request.args.get('dsstox_cid')
    s0    = float(request.args.get('s0', 0.1))
    k0    = int(request.args.get('k0', 12))
    fp    = request.args.get('fp','chm_mrgn')

    H = searchFP(cid,fp=fp,s0=s0,max_hits=k0,DB=DB)
    return jsonify(dict(result=dict(hits=H,n=len(H),fp=fp)))


@app.route('/api/genra/v3/viewChemNN/', methods=['GET'])
def viewChemNN():
    """
    Generate layout for nearest neighbours for chemical based on chm, bio or tox descriptors
    Specify one of: casrn or dsstox_cid
    ---
    tags:
      - viewChemNN
    parameters:
      - name: dsstox_cid
        in: query
        type: string
        default: null
        required: true
        paramType: query
        description: the DSSTOX CID of the input chemical
      - name: k0
        in: query
        type: int
        paramType: query
        description: The number of nearest neighbours to return
        defaultValue: 12
      - name: s0
        in: query
        type: float
        paramType: query
        description: The Jaccard similarity threshold
        defaultValue: 0.1
      - name: fp
        in: query
        type: string
        paramType: query
        enum:
          - chm_mrgn
          - chm_httr
          - chm_ct
          - bio_txct
          - bio_tx21
          - tox_txrf
        description: the type of fingerprint to use for similarity searching
      - name: sel_by
        in: query
        type: string
        paramType: query
        enum:
          - bio_txct
          - bio_tx21
          - tox_txrf
        description: select only those chemicals that have the corresponding data
        defaultValue: None
      - name: W
        in: query
        type: int
        paramType: query
        description: Width of canvas
        defaultValue: 600
      - name: H
        in: query
        type: int
        paramType: query
        description: Height of canvas
        defaultValue: 600
      - name: img_w
        in: query
        type: int
        paramType: query
        description: width of chemical svg image
        defaultValue: 60
      - name: img_h
        in: query
        type: int
        paramType: query
        description: height of chemical svg image
        defaultValue: 60

    responses:
      200:
        description: A radial layout of chemical hits
    """

    cid   = request.args.get('dsstox_cid')
    s0    = float(request.args.get('s0', 0.1))
    k0    = int(request.args.get('k0', 12)) + 1
    W     = float(request.args.get('H', 600))
    H     = float(request.args.get('W', 600))
    rs    = float(request.args.get('rs',1.0))
    img_w = float(request.args.get('img_w',60))
    img_h = float(request.args.get('img_h',60))
    rdst  = request.args.get('rdst','equal')
    fp    = request.args.get('fp','chm_mrgn')
    sel_by=request.args.get('sel_by')

    # Set up polar coords
    r_min = 50
    r_max = ifthen(W>H,W,H)*0.4
    C     = [0,0]
    O     = [-1*W*0.5,-1*H*0.5]
    th_tot= 1.9*math.pi
    th0   = 1.32*math.pi


    # Find NN
    Hits = searchFP(cid,fp=fp,s0=s0,max_hits=k0,DB=DB,sel_by=sel_by)

    if not Hits:
        Hits=[]
        return jsonify(dict())

    # View NN
    NN      = pd.DataFrame(Hits)
    NN['d'] = 1-NN.jaccard
    k0      = NN.shape[0]
    dth     = th_tot/k0

    NNq = NN.query("dsstox_cid=='%s'"%cid)
    NNh = NN.query("dsstox_cid!='%s'"%cid)
    NNh.sort_values(by='d',inplace=True)
    NN  = pd.concat((NNq,NNh))
    #NN.d[NN.d<=0.7]=0.7
    #NN['r'] = r_max*NN.d*rs
    # For now ...
    NN['r'] = r_max
    NN['th']= th0+dth*np.arange(0,k0)
    NN['x'] = NN.r*np.cos(NN.th)
    NN['y'] = NN.r*np.sin(NN.th)

    # Add a shorter loc for ending the edge
    NN['xb'] = 0.75*NN.r*np.cos(NN.th)
    NN['yb'] = 0.75*NN.r*np.sin(NN.th)

    # Root
    NN.ix[0,'r']=0
    NN.ix[0,'x']=C[0]
    NN.ix[0,'y']=C[1]
    NN.ix[0,'th']=0

    #Add image coordinates
    NN['v_img_w']=img_w
    NN['v_img_h']=img_h
    NN['v_img_x']=NN.x-img_w*0.5
    NN['v_img_y']=NN.y-img_h*0.5

    # Change to screen coordinates
    NN['v_x']=NN.x-O[0]
    NN['v_y']=NN.y-O[1]
    NN['xb'] =NN.xb-O[0]
    NN['yb'] =NN.yb-O[1]

    NN['v_img_x']=NN.v_img_x-O[0]
    NN['v_img_y']=NN.v_img_y-O[1]

    Vi= NN.ix[0]

    # Edges
    E2 = NN[['dsstox_cid','v_x','v_y','jaccard','xb','yb']].ix[1:].copy()
    E2.rename(columns=dict(dsstox_cid='vj',v_x='xj',v_y='yj'),inplace=True)
    E2['vi']=cid
    E2['xi']=Vi.v_x
    E2['yi']=Vi.v_y
    E2['lx']=0.5*(E2.xi+E2.xj)
    E2['ly']=0.5*(E2.yi+E2.yj)

    E2['label']=E2.jaccard.apply(lambda i:'%3.2f%s'% (i,fp[0]))

    return jsonify(dict(edges=E2.to_dict('records'),
                        nodes=NN.to_dict('records'),
                        k0=k0,s0=s0,
                        fp=fp,
                        W=W,H=H,
                        root=cid,
                        n=NN.shape[0]))

@app.route('/api/genra/v3/getChemNNSummary/', methods=['GET'])
def getChemNNSummary():
    """
    Summarize ct,bio,tox information for chemical
    Specify: dsstox_cid
    ---
    tags:
      - getChemNNSummary
    parameters:
      - name: dsstox_cid
        in: query
        type: string
        default: null
        required: true
        paramType: query
        description: the DSSTOX CID of the input chemical
      - name: k0
        in: query
        type: int
        paramType: query
        description: The number of nearest neighbours to return
        defaultValue: 12
      - name: s0
        in: query
        type: float
        paramType: query
        description: The Jaccard similarity threshold
        defaultValue: 0.1
      - name: fp
        in: query
        type: string
        paramType: query
        enum:
          - chm_mrgn
          - chm_httr
          - chm_ct
          - bio_txct
          - bio_tx21
          - tox_txrf
        description: the type of fingerprint to use for similarity searching
    responses:
      200:
        description: A summary of bio/tox for neighbouring chemicals
    """
    casrn = request.args.get('casrn')
    cid   = request.args.get('dsstox_cid')
    s0    = float(request.args.get('s0', 0.1))
    k0    = int(request.args.get('k0', 12)) + 1
    fp    = request.args.get('fp','chm_mrgn')

    # This dict contains the collections and fields to get the information
    COLLS = dict(chm_ct=dict(coll='chemotypes', projn="$chemotypes.n"),
                 bio_txct=dict(coll='bio_fp', projn={"$sum": ["$bio1.n", '$bio1_n.n']}),
                 bio_tx21=dict(coll='tox21_fp', projn="$t211.n"),
                 tox_txrf=dict(coll='tox5_fp', projn={"$sum": ["$tox_fpp1.n", "$tox_fpn1.n"]}))

    # Find NN
    Hits = searchFP(cid,fp=fp,s0=s0,max_hits=k0,DB=DB)

    if not Hits:
        Hits=[]
        return jsonify(dict(hits=[]))

    NN      = pd.DataFrame(Hits)
    #NN.rename(columns=dict(jaccard='sim'),inplace=True)

    CID = list(NN.dsstox_cid)

    S0 = getChemSummary(CID,MDB=DB,Colls=COLLS).reset_index()
    S0 = S0.merge(NN,left_on='dsstox_cid',right_on='dsstox_cid',how='outer')
    S0.fillna(0,inplace=True)

    return jsonify(dict(data=S0.to_dict('records'),
                        cols=dict(chem=['dsstox_cid','name','jaccard'],
                                  props=list(S0.columns.difference(['dsstox_cid','name','jaccard'])))))



@app.route('/api/genra/v3/viewChemNNSummary/', methods=['GET'])
def viewChemNNSummary():
    """
    Render summary of ct,bio,tox information for chemical
    Specify: dsstox_cid
    ---
    tags:
      - viewChemNNSummary
    parameters:
      - name: dsstox_cid
        in: query
        type: string
        default: null
        required: true
        paramType: query
        description: the DSSTOX CID of the input chemical
      - name: xlab
        in: query
        type: string
        default: name
        required: false
        paramType: query
        description: the name of the row label
      - name: ylab
        in: query
        type: string
        default: prop
        required: false
        paramType: query
        description: the name of the col label
      - name: k0
        in: query
        type: int
        paramType: query
        description: The number of nearest neighbours to return
        defaultValue: 12
      - name: s0
        in: query
        type: float
        paramType: query
        description: The Jaccard similarity threshold
        defaultValue: 0.1
      - name: fp
        in: query
        type: string
        paramType: query
        enum:
          - chm_mrgn
          - chm_httr
          - chm_ct
          - bio_txct
          - bio_tx21
          - tox_txrf
        description: the type of fingerprint to use for similarity searching
      - name: sel_by
        in: query
        type: string
        paramType: query
        enum:
          - bio_txct
          - bio_tx21
          - tox_txrf
        description: select only those chemicals that have the corresponding data
        defaultValue: None
      - name: W
        in: query
        type: float
        paramType: query
        description: canvas width
        defaultValue: 1000
      - name: dxy
        in: query
        type: float
        paramType: query
        description: the size of dx and dy for cell
        defaultValue: None
      - name: x0
        in: query
        type: float
        paramType: query
        description: x initial value
        defaultValue: 10
      - name: y0
        in: query
        type: float
        paramType: query
        description: y initial value
        defaultValue: 10
      - name: H
        in: query
        type: float
        paramType: query
        description: canvas height
        defaultValue: 1000
      - name: obj
        in: query
        type: string
        enum:
          - rect
          - circle
        paramType: query
        description:
        defaultValue: 1
    responses:
      200:
        description: A visual summary of bio/tox for neighbouring chemicals
    """
    cid   = request.args.get('dsstox_cid')
    s0    = float(request.args.get('s0', 0.1))
    k0    = int(request.args.get('k0', 12)) + 1
    fp    = request.args.get('fp','chm_mrgn')
    H     = float(request.args.get('W', 1000))
    W     = float(request.args.get('H', 1000))
    dxy   = request.args.get('dxy',20)
    x0    = float(request.args.get('x0', 50))+60
    y0    = float(request.args.get('y0', 50))+60
    rs    = float(request.args.get('rs', 1.0))
    xlab  = request.args.get('xlab', 'name')
    ylab  = request.args.get('ylab', 'prop')
    obj   = request.args.get('obj', 'rect')
    sel_by=request.args.get('sel_by')

    if dxy: dxy = float(dxy)
    # This dict contains the collections and fields to get the information
    # This dict contains the collections and fields to get the information

    COLLS = dict(chm_ct=dict(coll='chemotypes', projn="$chemotypes.n"),
                 bio_txct=dict(coll='bio_fp', projn={"$sum":["$bio1.n",'$bio1_n.n']}),
                 bio_tx21=dict(coll='tox21_fp', projn="$t211.n"),
                 tox_txrf=dict(coll='tox5_fp', projn={"$sum":["$tox_fpp1.n","$tox_fpn1.n"]}))



    Hits = searchFP(cid,fp=fp,s0=s0,max_hits=k0,DB=DB,sel_by=sel_by)
    print(Hits)
    if not Hits:
        print('yeah')
        return jsonify(dict(hits=[]))

    NN      = pd.DataFrame(Hits)

    CID = list(NN.dsstox_cid)
    S0 = getChemSummary(CID,MDB=DB,Colls=COLLS).reset_index()
    S0 = S0.merge(NN,left_on='dsstox_cid',right_on='dsstox_cid')
    S0.set_index(list(NN.columns),inplace=True)
    S0.sort_index(level='jaccard',ascending=False,inplace=True)
    S1 = S0.reset_index().drop(['dsstox_cid', 'dsstox_sid', 'jaccard'], axis=1)
    S1.set_index('name',inplace=True)

    HM = dict(circle=[],rect=[],text=[],line=[])
    if obj=='circle':
        HM['circle'] = df2circhm(S0,rs=1.3,W=W,H=H,x0=x0,y0=y0,cmap=cm.inferno_r).to_dict('records')
    elif obj=='rect':
        HM['rect'] = df2squarehm(S0,sep=1,W=W,H=H,x0=x0,y0=y0,cmap=cm.inferno_r).to_dict('records')
    X=df2axes(S1,W=W,H=H,x0=x0,y0=y0,xlab=xlab,ylab=ylab)
    HM['text'] = X['R0'].to_dict('records') + X['C0'].to_dict('records')
    return jsonify(dict(heatmap=HM))


@app.route('/api/genra/v3/viewChemNNDetails/', methods=['GET'])
def viewChemNNDetails():
    """
    Summarize ct,bio,tox information for chemical
    Specify: dsstox_cid
    ---
    tags:
      - viewChemNNDetails
    parameters:
      - name: dsstox_cid
        in: query
        type: string
        default: null
        required: true
        paramType: query
        description: the DSSTOX CID of the input chemical
      - name: filt_rows
        in: query
        type: string
        default: null
        required: false
        paramType: query
        description: text pattern to filter the row sumrs_by values
      - name: rows_per_page
        in: query
        type: int
        default: null
        required: false
        paramType: query
        description: number of rows per page
      - name: k0
        in: query
        type: int
        paramType: query
        description: The number of nearest neighbours to return
        defaultValue: 12
      - name: s0
        in: query
        type: float
        paramType: query
        description: The Jaccard similarity threshold
        defaultValue: 0.1
      - name: fp
        in: query
        type: string
        paramType: query
        enum:
          - chm_mrgn
          - chm_httr
          - chm_ct
          - bio_txct
          - bio_tx21
          - tox_txrf
        description: the type of fingerprint to use for similarity searching
      - name: sel_by
        in: query
        type: string
        paramType: query
        enum:
          - bio_txct
          - bio_tx21
          - tox_txrf
        description: select only those chemicals that have the corresponding data
        defaultValue: None
      - name: summarise
        in: query
        type: string
        paramType: query
        enum:
          - bio_txct
          - bio_tx21
          - tox_txrf
        description: the type of information to be summarised where bio_* are in vitro effects and tox_* are in vivo effects
      - name: sumrs_by
        in: query
        type: string
        paramType: query
        enum:
          - gene_name
          - gene_symbol
          - target_family
          - bio_process
          - cell
          - tissue
          - organ
          - organism
          - study
          - bio_fp
          - tox_fp
        description: How the information will be summarised across the levels of biological organisation
      - name: xlab
        in: query
        type: string
        default: name
        required: false
        paramType: query
        description: the name of the row label
      - name: ylab
        in: query
        type: string
        default: prop
        required: false
        paramType: query
        description: the name of the col label
      - name: W
        in: query
        type: float
        paramType: query
        description: canvas width
        defaultValue: 1000
      - name: dxy
        in: query
        type: float
        paramType: query
        description: the size of dx and dy for cell
        defaultValue: 10
      - name: x0
        in: query
        type: float
        paramType: query
        description: x initial value
        defaultValue: 10
      - name: y0
        in: query
        type: float
        paramType: query
        description: y initial value
        defaultValue: 10
      - name: H
        in: query
        type: float
        paramType: query
        description: canvas height
        defaultValue: 1000
    responses:
      200:
        description: A summary of bio/tox for neighbouring chemicals
    """
    casrn = request.args.get('casrn')
    cid   = request.args.get('dsstox_cid')
    s0    = float(request.args.get('s0', 0.1))
    k0    = int(request.args.get('k0', 12)) + 1
    fp    = request.args.get('fp','chm_mrgn')
    summarise=request.args.get('summarise')
    sumrs_by=request.args.get('sumrs_by')
    filt_rows=request.args.get('filt_rows','')
    sel_by=request.args.get('sel_by')
    xlab  = sumrs_by
    rowspp = request.args.get('rows_per_page')
    ylab = request.args.get('xlab', 'name')
    H     = float(request.args.get('W', 1000))
    W     = float(request.args.get('H', 1000))
    dxy   = float(request.args.get('dxy',20))
    x0    = float(request.args.get('x0', 50))+60
    y0    = float(request.args.get('y0', 50))+60

    R1 = pd.DataFrame()
    if summarise == 'bio_txct':
        R1 = getChemToxCastNNSummary(cid,s0=s0,k0=k0,fp=fp,MDB=DB,sel_by=sel_by)
    elif summarise == 'bio_tx21':
        R1 = getChemTox21NNSummary(cid,s0=s0,k0=k0,fp=fp,MDB=DB,sel_by=sel_by)

    elif summarise == 'tox_txrf':
        R1 = getChemToxRefNNSummary(cid,s0=s0,k0=k0,fp=fp,MDB=DB,sel_by=sel_by)

    if R1.shape[0]==0: return jsonify(dict(heatmap=None,view=None))

    R1['n']=1
    R1.drop_duplicates(inplace=True)
    R1.fillna('',inplace=True)
    xmax=0
    ymax=0
    HM = dict(circle=[],rect=[],text=[],line=[])
    if sumrs_by in R1.columns:
        R11 = R1.pivot_table(index=['dsstox_cid','name','jaccard'],
                            columns=sumrs_by,
                            values='n',
                            aggfunc=len,fill_value=0)
        if cid in R11.index.get_level_values('dsstox_cid'):
            R2=R11
        else:
            target=DB['compound'].find_one({'dsstox_cid':cid})
            target_index=[(cid,target['name'],1)]
            R2_index=pd.Index(target_index+list(R11.index.values))
            R2_index.names=['dsstox_cid','name','jaccard']
            R2=R11.reindex_axis(R2_index,fill_value=0)
        #print(R2)
        # Sort columns and rows
        R2.sort_index(level=2,ascending=False,inplace=True)
        R2 = R2.reset_index().drop(['jaccard'],axis=1)
        R2.set_index(['dsstox_cid','name'],inplace=True)
        R2.index.name='name'
        R2 = pd.DataFrame(R2.T)

        # Sort rows by hits
        I = R2.sum(axis=1)
        I.sort_values(ascending=False)
        R2 = R2.ix[I.index]

        # Filter rows
        if filt_rows!=None and len(filt_rows)>1:
            I1 = R2.index.str.contains(filt_rows,case=False)
            R2 = R2.ix[I1]

        if R2.shape[0]==0: return jsonify(dict(heatmap=None,view=None))

        # Bootstrap Tooltips
        labels = list(R2.index.values)
        TTs = getFPHelp(DB, labels)
        X = df2squarehm(R2,sep=1,W=W,H=H,dxy=dxy,x0=x0,y0=y0,cmap=cm.inferno_r)
        xmax,ymax = X.x.max(),X.y.max()
        HM['rect']=X.to_dict('records')
        #for r in HM['rect']:
        #    r['label']=r[sumrs_by]
        X = df2axes(R2, TTs, W=W, H=H, dxy=dxy, x0=x0, y0=y0, ylab=xlab, xlab=ylab)
        # The xlab and ylab depend on whether R2 has been transposed or not ...

        #xmax = xmax if X.x.max()<xmax else X.x.max()
        #ymax = ymax if X.y.max()<ymax else X.y.max()
        HM['text']=X['R0'].to_dict('records')+X['C0'].to_dict('records')

        xmax,ymax = int(1.2*xmax),int(1.2*ymax)

    return jsonify(dict(heatmap=HM,view=dict(width=xmax,height=ymax)))

@app.route('/api/genra/v3/viewChemNNDetailsPages/', methods=['GET'])
def viewChemNNDetailsPages():
    """
    Summarize ct,bio,tox information for chemical
    Specify: dsstox_cid
    ---
    tags:
      - viewChemNNDetailsPages
    parameters:
      - name: dsstox_cid
        in: query
        type: string
        default: null
        required: true
        paramType: query
        description: the DSSTOX CID of the input chemical
      - name: filt_rows
        in: query
        type: string
        default: null
        required: false
        paramType: query
        description: text pattern to filter the row sumrs_by values
      - name: rows_per_page
        in: query
        type: int
        default: null
        required: false
        paramType: query
        description: number of rows per page
      - name: k0
        in: query
        type: int
        paramType: query
        description: The number of nearest neighbours to return
        defaultValue: 12
      - name: s0
        in: query
        type: float
        paramType: query
        description: The Jaccard similarity threshold
        defaultValue: 0.1
      - name: fp
        in: query
        type: string
        paramType: query
        enum:
          - chm_mrgn
          - chm_httr
          - chm_ct
          - bio_txct
          - bio_tx21
          - tox_txrf
        description: the type of fingerprint to use for similarity searching
      - name: sel_by
        in: query
        type: string
        paramType: query
        enum:
          - bio_txct
          - bio_tx21
          - tox_txrf
        description: select only those chemicals that have the corresponding data
        defaultValue: None
      - name: summarise
        in: query
        type: string
        paramType: query
        enum:
          - bio_txct
          - bio_tx21
          - tox_txrf
        description: the type of information to be summarised where bio_* are in vitro effects and tox_* are in vivo effects
      - name: sumrs_by
        in: query
        type: string
        paramType: query
        enum:
          - gene_name
          - gene_symbol
          - target_family
          - bio_process
          - cell
          - tissue
          - organ
          - organism
          - study
          - bio_fp
          - tox_fp
        description: How the information will be summarised across the levels of biological organisation
      - name: xlab
        in: query
        type: string
        default: name
        required: false
        paramType: query
        description: the name of the row label
      - name: ylab
        in: query
        type: string
        default: prop
        required: false
        paramType: query
        description: the name of the col label
      - name: W
        in: query
        type: float
        paramType: query
        description: canvas width
        defaultValue: 1000
      - name: dxy
        in: query
        type: float
        paramType: query
        description: the size of dx and dy for cell
        defaultValue: 10
      - name: x0
        in: query
        type: float
        paramType: query
        description: x initial value
        defaultValue: 10
      - name: y0
        in: query
        type: float
        paramType: query
        description: y initial value
        defaultValue: 10
      - name: H
        in: query
        type: float
        paramType: query
        description: canvas height
        defaultValue: 1000
    responses:
      200:
        description: A summary of bio/tox for neighbouring chemicals
    """
    casrn = request.args.get('casrn')
    cid   = request.args.get('dsstox_cid')
    s0    = float(request.args.get('s0', 0.1))
    k0    = int(request.args.get('k0', 12)) + 1
    fp    = request.args.get('fp','chm_mrgn')
    summarise=request.args.get('summarise')
    sumrs_by=request.args.get('sumrs_by')
    filt_rows=request.args.get('filt_rows','')
    sel_by=request.args.get('sel_by')
    xlab  = sumrs_by
    rowspp = int(request.args.get('rows_per_page',10))
    ylab = request.args.get('xlab', 'name')
    H     = float(request.args.get('W', 1000))
    W     = float(request.args.get('H', 1000))
    dxy   = float(request.args.get('dxy',20))
    x0    = float(request.args.get('x0', 50))+60
    y0    = float(request.args.get('y0', 50))+60

    R1 = pd.DataFrame()
    if summarise == 'bio_txct':
        R1 = getChemToxCastNNSummary(cid,s0=s0,k0=k0,fp=fp,MDB=DB,sel_by=sel_by)
    elif summarise == 'bio_tx21':
        R1 = getChemTox21NNSummary(cid,s0=s0,k0=k0,fp=fp,MDB=DB,sel_by=sel_by)

    elif summarise == 'tox_txrf':
        R1 = getChemToxRefNNSummary(cid,s0=s0,k0=k0,fp=fp,MDB=DB,sel_by=sel_by)

    if R1.shape[0]==0: return jsonify({1:dict(heatmap=None,view=None)})

    R1['n']=1
    R1.drop_duplicates(inplace=True)
    R1.fillna('',inplace=True)
    HM = dict(circle=[],rect=[],text=[],line=[])
    if sumrs_by in R1.columns:
        R11 = R1.pivot_table(index=['dsstox_cid','name','jaccard'],
                            columns=sumrs_by,
                            values='n',
                            aggfunc=len,fill_value=0)
        if cid in R11.index.get_level_values('dsstox_cid'):
            R2=R11
        else:
            target=DB['compound'].find_one({'dsstox_cid':cid})
            target_index=[(cid,target['name'],1)]
            R2_index=pd.Index(target_index+list(R11.index.values))
            R2_index.names=['dsstox_cid','name','jaccard']
            R2=R11.reindex_axis(R2_index,fill_value=0)
        # Sort columns and rows
        R2.sort_index(level=2,ascending=False,inplace=True)
        R2 = R2.reset_index().drop(['jaccard'], axis=1)
        R2.set_index(['dsstox_cid', 'name'], inplace=True)
        R2.index.name = 'name'
        R2 = pd.DataFrame(R2.T)

        # Sort rows by hits
        I = R2.sum(axis=1)
        I.sort_values(ascending=False)
        R2 = R2.ix[I.index]

        # Filter rows
        if filt_rows!=None and len(filt_rows)>1:
            I1 = R2.index.str.contains(filt_rows,case=False)
            R2 = R2.ix[I1]

        if R2.shape[0]==0: return jsonify({1:dict(heatmap=None,view=None)})

        #Bootstrap Tooltips
        labels=list(R2.index.values)
        TTs=getFPHelp(DB,labels)

        # Split R2 in to pages:
        page_num = 0
        Pages={1:dict(heatmap=None,view=None)}
        for r_i in range(0,R2.shape[0],rowspp):
            HM = dict(circle=[],rect=[],text=[],line=[])
            page_num+=1
            r_f = r_i+rowspp-1
            if r_f > R2.shape[0]-1: r_f = R2.shape[0]-1
            R2_p = R2.ix[R2.index[r_i]:R2.index[r_f]]
            if R2_p.shape[0]==0: continue
            X = df2squarehm(R2_p,sep=1,W=W,H=H,dxy=dxy,x0=x0,y0=y0,cmap=cm.inferno_r)
            HM['rect']=X.to_dict('records')
            #HM['data']=dict(rows=list(R2_p.index),cols=list(R2_p.columns))
            X = df2axes(R2_p,TTs,W=W,H=H,dxy=dxy,x0=x0,y0=y0,ylab=xlab,xlab=ylab)
            text=X['R0'].to_dict('records')+X['C0'].to_dict('records')
            xmax=max([t['x'] for t in text])
            ymax=max(t['y'] for t in text)
            # The xlab and ylab depend on whether R2 has been transposed or not ...
            #xmax = xmax if X.x.max()<xmax else X.x.max()
            #ymax = ymax if X.y.max()<ymax else X.y.max()

            HM['text'] = text
            xmax,ymax = int(1.2*xmax),int(1.2*ymax)
            Pages[page_num]=dict(heatmap=HM,view=dict(width=xmax,height=ymax))

    #return jsonify(dict(Pages=Pages,Data=dict(rows=list(R2.index),cols=list(R2.columns))))
    return jsonify(Pages)


@app.route('/api/genra/v3/getChemNNToxData/', methods=['GET'])
def getChemNNToxData():
    """
    Get tox information for chemical nearest neighbours for RA
    Specify: dsstox_cid
    ---
    tags:
      - getChemNNToxData
    parameters:
      - name: dsstox_cid
        in: query
        type: string
        default: null
        required: false
        paramType: query
        description: the DSSTOX CID of the input chemical
      - name: filt_rows
        in: query
        type: string
        default: null
        required: false
        paramType: query
        description: text pattern to filter the row sumrs_by values
      - name: k0
        in: query
        type: int
        paramType: query
        description: The number of nearest neighbours to return
        defaultValue: 12
      - name: s0
        in: query
        type: float
        paramType: query
        description: The Jaccard similarity threshold
        defaultValue: 0.1
      - name: pos0
        in: query
        type: int
        paramType: query
        description: The number positives for each toxicity classification
        defaultValue: 1
      - name: neg0
        in: query
        type: int
        paramType: query
        description: The number negatives for each toxicity classification
        defaultValue: 1
      - name: fp
        in: query
        type: string
        paramType: query
        enum:
          - chm_mrgn
          - chm_httr
          - chm_ct
          - bio_txct
          - bio_tx21
          - tox_txrf
        description: the type of fingerprint to use for similarity searching
      - name: sel_by
        in: query
        type: string
        paramType: query
        enum:
          - bio_txct
          - bio_tx21
          - tox_txrf
        description: select only those chemicals that have the corresponding data
        defaultValue: None
    responses:
      200:
        description: details of tox for neighbouring chemicals
    """
    cid   = request.args.get('dsstox_cid')
    s0    = float(request.args.get('s0', 0.1))
    k0    = int(request.args.get('k0', 12)) + 1
    fp    = request.args.get('fp','chm_mrgn')
    pos0  = int(request.args.get('pos0', 1))
    neg0  = int(request.args.get('neg0', 1))
    filt_rows=request.args.get('filt_rows','')
    sel_by=request.args.get('sel_by')

    RA = getChemToxRefNNData(cid,s0=s0,k0=k0,fp=fp,MDB=DB,neg_min=neg0,pos_min=pos0,
                             sel_by=sel_by,filt_by=filt_rows)
    if not RA: return jsonify(dict())

    RA = {k:RA[k] for k in ['cols','row_labs','col_labs','units','nn_opts']}
    return jsonify(RA)

@app.route('/api/genra/v3/runGenRAPerfPred', methods=['GET','POST'])
def runGenRAPerfPred():
    """
    Run GenRA performance analysis and prediction
    Specify: dsstox_cid
    ---
    tags:
      - runGenRAPerfPred
    parameters:
      - name: dsstox_cid
        in: query
        type: string
        default: null
        required: false
        paramType: query
        description: the DSSTOX CID of the input chemical
      - name: tox
        in: query
        type: list
        default: null
        required: false
        paramType: query
        description:  list of toxicities for evaluation of activities
      - name: k0
        in: query
        type: int
        paramType: query
        description: The number of nearest neighbours to return
        defaultValue: 12
      - name: s0
        in: query
        type: float
        paramType: query
        description: The Jaccard similarity threshold
        defaultValue: 0.01
      - name: pos0
        in: query
        type: int
        paramType: query
        description: The number positives for each toxicity classification
        defaultValue: 1
      - name: neg0
        in: query
        type: int
        paramType: query
        description: The number negatives for each toxicity classification
        defaultValue: 1
      - name: fp
        in: query
        type: string
        paramType: query
        enum:
          - chm_mrgn
          - chm_httr
          - chm_ct
        description: the type of fingerprint to use for similarity searching
      - name: sel_by
        in: query
        type: string
        paramType: query
        enum:
          - tox_txrf
        description: select only those chemicals that have the corresponding data
        defaultValue: None
    responses:
      200:
        description: details of tox for neighbouring chemicals
    """
    # Post request comes in request.data

    #print(request.data,file=sys.stderr)

    Data = json.loads(request.data)
    cid   = Data.get('dsstox_cid')
    s0    = float(Data.get('s0', 0.01))
    k0    = int(Data.get('k0', 12)) + 1
    fp    = Data.get('fp','chm_mrgn')
    pos0  = int(Data.get('pos0', 1))
    neg0  = int(Data.get('neg0', 1))
    sel_by= Data.get('sel_by')
    CID   = Data.get('chem_inc')
    Y     = Data.get('tox_inc')

    #print("cid %s\nfp %s\nk0 %d\ns0 %3.2f" % (cid,fp,k0,s0),file=sys.stderr)

    Res = runGenRA(cid,CID=CID,Y=Y,
                   DB=DB,fp_x=fp,fp_y='toxp_txrf',sel_by=sel_by,
                   metric='jaccard',k0=k0,s0=s0,pred=True,ret='df',n_perm=200)
    #Res_df = pd.DataFrame(Res)
    #Res_df.fillna(0,inplace=True)
    #Res_df.to_csv(sys.stderr)
    #return jsonify(Res_df.to_dict('records'))
    #print(json.dumps({'pred':Res}),file=sys.stderr)
    return jsonify({'pred':Res})

@app.route('/api/genra/v3/viewChem/<cid>.svg')
def viewChemSvg(cid):
    """
    View the input chemical in svg format
    ---
    tags:
      - viewChemSvg
    parameters:
      - name: cid
        in: query
        type: string
        description: a partial string containing the chemical DSSTOX CID
    responses:
      200:
        description: An SVG rendering of the chemical

    """
    C = DB.compound.find_one(dict(dsstox_cid=cid),{'viz':1})
    svg = None
    if C and C.has_key('viz'):
        svg = C['viz']
    else:
        svg = NO_SVG
    svg = svg.replace('<rect x="0" y="0" width="100" height="100" style="fill:rgb(100%,100%,100%);fill-opacity:1;stroke:none;"/>','')

    response = make_response(svg)
    response.content_type = 'image/svg+xml'
    return response

@app.route('/api/genra/v3/viewChemGlyph/<cid>.svg')
def viewChemGlyph(cid):
    C = DB.compound.find_one(dict(dsstox_cid=cid),{'viz':1})
    svg = None
    if C and C.has_key('viz'):

        svg = re.sub('>(\S+)</svg:text>',
                     '>&#8226;</svg:text>',
                     C['viz'])
        svg = re.sub('encoding="iso-8859-1"',
                     'encoding="UTF-8"',
                     svg)
        svg = re.sub('font-size="7.00"',
                     'font-size="20.00"',
                     svg)

        #svg = re.sub('stroke-width="1"></svg:line>',
        #             'stroke-width="1.5"></svg:line>',
        #             svg)
    else:
        svg = NO_SVG


    response = make_response(svg)
    response.content_type = 'image/svg+xml'
    return response

@app.route('/api/genra/v3/exportSvg/', methods=['POST'])
def export():
    svg_xml = request.data
    #response = Response(svg_xml, mimetype="image/svg+xml")
    #print len(svg_xml),svg_xml[:100]
    response = make_response(svg_xml)
    response.content_type = 'image/svg+xml'
    response.headers["Content-Disposition"] = "attachment"

    return response

# DEVEL:
# Uncomment the following lines ...

if __name__ == '__main__':

    # This makes sure Flask will restart service if any of the static files change
    DIR=os.getcwd()
    EF = [ef for ef in reduce(lambda x,y: x+y,[[d+'/'+i for i in F]
                                               for d,D,F in os.walk(DIR)])
          if not re.search('git|~$|\#$|pyc$',ef)]
    app.debug=True
    app.run(host='localhost',port=6008,extra_files=EF)


