import unittest
import numpy as np


def qe_activity(t):
    alpha=float(np.trace(t)/3.0)
    beta2=((t[0,0]-t[1,1])**2+(t[0,0]-t[2,2])**2+(t[1,1]-t[2,2])**2+6.0*(t[0,1]**2+t[0,2]**2+t[1,2]**2))/2.0
    return 45.0*alpha*alpha+7.0*beta2


class RamanDegenerateSubspaceTests(unittest.TestCase):
    def test_complete_optical_subspace_activity_is_basis_invariant(self):
        tensors=np.asarray([[[1.,0.,0.],[0.,-1.,0.],[0.,0.,0.]],[[0.,0.,1.],[0.,0.,0.],[1.,0.,0.]],[[0.,2.,0.],[2.,0.,0.],[0.,0.,0.]]])
        theta=0.37; phi=0.61
        a=np.array([[np.cos(theta),-np.sin(theta),0.],[np.sin(theta),np.cos(theta),0.],[0.,0.,1.]])
        b=np.array([[1.,0.,0.],[0.,np.cos(phi),-np.sin(phi)],[0.,np.sin(phi),np.cos(phi)]])
        o=a@b
        rotated=np.einsum("ij,jab->iab",o,tensors)
        self.assertAlmostEqual(sum(qe_activity(x) for x in tensors),sum(qe_activity(x) for x in rotated),places=10)
        self.assertFalse(np.allclose(tensors,rotated))

if __name__ == "__main__": unittest.main()
