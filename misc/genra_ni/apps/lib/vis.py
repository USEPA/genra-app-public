from itertools import product
import matplotlib.cm as cm
import matplotlib as mpl
import pandas as pd
import numpy as np


def makeScaled(X):
    """Input and Output are pd.Series. Remove outliers and scale numbers for [0,1]. If only [0,1] then does nothing """
    # If there are only {0,1} values then there's nothing to do
    if len(set(X).difference([0, 1])) == 0:
        return X

    return (X - X.min()) / (X.max() - X.min())
    
def makeColored(X,cmap=cm.RdYlBu_r,grey=False):
    Nrm = mpl.colors.Normalize(vmin=X.min(),vmax=X.max())
    myCol = cm.ScalarMappable(Nrm,cmap=cmap) 

    def val2col(i):
        rgb = map(lambda c: int(255*c),myCol.to_rgba(i))
        return '#%02x%02x%02x' % tuple(rgb[:3])
    
    Y =  X.apply(val2col)
    if grey:
        Y[X==0]=grey

    return Y

def df2cartesian(DF,x0=10,y0=10,W=100,H=100,m0=2,cmap=cm.RdYlBu_r,aspect='equal',         
                 dxy=None):
    Ri = DF.index
    Ci = DF.columns
    nr,nc = DF.shape
    dx =  None
    dy =  None
    if dxy:
        dx=dxy
        dy=dxy
    else:
        dx = (W-x0)/nc
        dy = (H-y0)/nr
        
    ind_name = list(DF.index.names)
    col_name = list(DF.columns.names)
    
    if aspect=='equal':
        if dx>dy:
            dx=dy
        else:
            dy=dx

    def getInd(xx):
        if type(xx)==tuple:
            return list(xx)
        else:
            return [xx]
    Y = pd.DataFrame(map(lambda (i,j): [i,j]+getInd(Ri[i])+getInd(Ci[j])+[DF.ix[Ri[i],Ci[j]]],
                         product(range(nr),range(nc))),
                     columns=['i','j']+ind_name + col_name +['val'])
    Y['x']=x0+Y.j*dx
    Y['y']=y0+Y.i*dy
    Y['eid']= Y.apply(lambda z: "cell %d:%d" % (z['i'],z['j']),axis=1)
    print(Y.columns.values)
    print(Y['val'])
    Y['scaled'] = makeScaled(Y.val)
    Y['color']  = makeColored(Y.scaled,cmap=cmap,grey='#efefef')
    Y['dx'] = dx
    Y['dy'] = dy

    Y.fillna(0,inplace=True)

    return Y


def df2axes(DF,TT_DF=pd.DataFrame(),xlab=None,ylab=None,**kwargs):
    """
    The input DF should not be multiindex 
    xlab: required
    ylab: required
    """
    if len(DF.index.names)>1: return

    Y = df2cartesian(DF,**kwargs)
    row_name = DF.index.name
    col_name = DF.columns.name

    # Column labs
    C0 = Y[[col_name,'x','dx','dy']].drop_duplicates()
    C0.rename(columns={col_name:'label'},inplace=True)

    C0['x']=C0.x+0.5*C0.dx
    C0['y']=Y.y.min()-5
    C0['pos']='end'
    C0['rot']=90
    C0['fs']=10
    C0['color']='#787878'

    # Row labs
    R0 = Y[[row_name,'y','dx','dy']].drop_duplicates()
    R0.rename(columns={row_name:'label'},inplace=True)

    R0['y']=R0.y+0.5*R0.dy
    R0['x']=Y.x.min()-5
    R0['pos']='end'
    R0['rot']=0
    R0['fs']=10
    R0['color']='#1111ff'
    R0 = R0.join(TT_DF, on='label')
    
    #return R0.to_dict('record')+C0.to_dict('record')
    return dict(C0=C0,R0=R0)

def df2axesOld(DF,**kwargs):
    Y = df2cartesian(DF,**kwargs)
    row_name = DF.index.name
    col_name = DF.columns.name

    C0 = Y[[col_name,'x','dx','dy']].drop_duplicates()
    C0.rename(columns={col_name:'label'},inplace=True)

    R0 = Y[[row_name,'y','dx','dy']].drop_duplicates()
    R0.rename(columns={row_name:'label'},inplace=True)

    R0['y']=R0.y+0.5*R0.dy
    R0['x']=Y.x.min()
    R0['pos']='end'
    R0['rot']=0
    R0['fs']=10
    C0['x']=C0.x+0.5*C0.dx
    C0['y']=Y.y.min()
    C0['pos']='end'
    C0['rot']=90
    C0['fs']=10

    AX = pd.concat((R0,C0))
    AX['color']='#898989'
    
    return AX.to_dict('record')
    
    
def df2circhm(DF,rs=1.0,rlog=False,**kwargs):
    Y = df2cartesian(DF,**kwargs)
    dx = Y.dx[0]
    dy = Y.dy[0]
    dr = rs*0.5*np.sqrt(dx**2+dy**2)
    Y['r'] = Y.scaled * rs
    #Y.r[Y.r==0]=1e-6
    if rlog: 
        Y['r'] = np.log2(Y.r)
        #Y.r[Y.r<0]=0

    Y['obj']='circle'
    return Y

def df2squarehm(DF,sep=2,**kwargs):
    Y = df2cartesian(DF,**kwargs)    
    Y['width']  = Y.dx-sep
    Y['height'] = Y.dy-sep
    Y['obj']='rect'
    
    return Y

