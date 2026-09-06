from PIL import Image
from pathlib import Path
import numpy as np
for path in Path(__file__).parent.joinpath('raw').glob('*.png'):
    a=np.array(Image.open(path).convert('RGB'))
    border=np.concatenate((a[0],a[-1],a[:,0],a[:,-1]))
    print(path.name, 'corner', a[0,0].tolist(), 'border range', border.min(axis=0).tolist(),border.max(axis=0).tolist())
