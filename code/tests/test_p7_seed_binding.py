import copy
import numpy as np
import torch
from core.models import to_batch,state_hash
from scripts.run_p7_seed_bound import seed_bound_adapt,install_seed_binding


class DropoutToy(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.layers=torch.nn.Sequential(torch.nn.Linear(2,4),torch.nn.Dropout(.3),torch.nn.Linear(4,1))

    def forward(self,x):
        return self.layers(x[:,-1])


def test_p7_dropout_pairing_independent_of_executor_order():
    torch.manual_seed(7)
    model=DropoutToy()
    xy=to_batch(np.ones((10,96,2),dtype=np.float32),np.zeros((10,1),dtype=np.float32),"update")
    before=state_hash(model)
    first=seed_bound_adapt(model,xy,50,19)
    torch.rand(77)
    second=seed_bound_adapt(model,xy,50,19)
    assert state_hash(first)==state_hash(second)
    assert state_hash(model)==before


def test_p7_dropout_binding_restores_caller_rng():
    torch.manual_seed(71)
    model=DropoutToy()
    xy=to_batch(np.ones((10,96,2),dtype=np.float32),np.zeros((10,1),dtype=np.float32),"update")
    rng=torch.get_rng_state().clone()
    seed_bound_adapt(model,xy,10,24)
    assert torch.equal(rng,torch.get_rng_state())


def test_p7_spawn_worker_binding_installed():
    install_seed_binding()
    import core.p7 as p7
    import core.p6 as p6
    import scripts.run_p7 as runner
    assert p7.adapt is p6.adapt is runner.adapt is seed_bound_adapt
