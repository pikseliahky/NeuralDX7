#%%
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.optim.lr_scheduler import StepLR
from pathlib import Path
from torch.utils.data import Subset as DataSubset
from sklearn.model_selection import train_test_split
import numpy as np
from dx7_constants import VOICE_PARAMETER_RANGES, ARTIFACTS_ROOT, VOICE_KEYS
import numpy as np
N_PARAMS = len(VOICE_PARAMETER_RANGES)
MAX_VALUE = max([max(i) for i in VOICE_PARAMETER_RANGES.values()]) + 1
#%%

# class DataHandler()
#     def __init__(self, data_file, root=ARTIFACTS_ROOT):

#         if not isinstance(root, Path):
#             root = Path(root).expanduser()

#         data = np.load(ARTIFACTS_ROOT.joinpath(patch_file))



class DX7Dataset():
    

    def __init__(self, data_file='dx7.npy', root=ARTIFACTS_ROOT):

        if not isinstance(root, Path):
            root = Path(root).expanduser()

        self.data = np.load(root.joinpath(data_file)) 
        

    def __getitem__(self, index):

        item = torch.tensor(self.data[index].item()).long()

        return item
    def __len__(self):
        return len(self.data)


#%%

#%%
class Net(nn.Module):
    def __init__(self, latent_dim=8, n_params=N_PARAMS, max_value=MAX_VALUE):
        super(Net, self).__init__()

        self.n_params = n_params
        self.max_value = max_value

        self.embedder = nn.Embedding(max_value, 128)

        self.dec = nn.ModuleList(
            [nn.LSTM(128, 128, batch_first=True),
            nn.GELU(),
            nn.Dropout(0.4),
            nn.LSTM(128, 128, batch_first=True),]
        )

        self.register_buffer('mask', self.generate_mask())

    def network(self, x, network):

        lstm, gelu, drop, lstm2 = network

        x_1, _ = lstm(x)
        if lstm.bidirectional == True:
            x_1 = torch.stack(x_1.chunk(2, -1)).sum(0)

        x_in = gelu(drop(x_1)) + x
        x_2, _ = lstm2(x)

        if lstm.bidirectional == True:
            x_2 = torch.stack(x_2.chunk(2, -1)).sum(0)

        x = gelu(drop(x_2)) * x_in

        return x

    @staticmethod
    def generate_mask():
        
        mask_item_f = lambda x: torch.arange(MAX_VALUE) <= max(x) 
        mapper = map(mask_item_f, map(VOICE_PARAMETER_RANGES.get, VOICE_KEYS))

        return torch.stack(list(mapper))

    def forward(self, x):
        
        x = self.embedder(x)
        x_z_sub_1 = torch.cat([x[:,[0]]*0, x[:,:-1]], dim=-2)


        x_hat = self.network(x_z_sub_1, self.dec)

        x_hat = torch.masked_fill(x_hat, ~self.mask, -1e9)
        return x_hat

    def generate(self, z, t=1.):

        x_hat = self.dec(z)
        x_hat = x_hat.reshape(-1, self.n_params, self.max_value)
        x_hat = torch.masked_fill(x_hat, ~self.mask, -float('inf'))

        x_hat = torch.distributions.Categorical(logits=x_hat / t)

        return x_hat
#%%
def train(model, device, train_loader, optimizer, epoch):
    model.train()
    for batch_idx, (data) in enumerate(train_loader):
        data = data.to(device)
        optimizer.zero_grad()
        output = model(data)
        loss = F.cross_entropy(output.transpose(-1,-2), data)

        loss.backward()
        optimizer.step()
        if batch_idx % 100 == 0:
            print('Train Epoch: {} [{}/{} ({:.0f}%)]\tLoss: {:.6f}\tKL: {:.3f}'.format(
                epoch, batch_idx * len(data), len(train_loader.dataset),
                100. * batch_idx / len(train_loader), loss.item(), 0))


def test(model, device, test_loader):
    model.eval()
    test_loss = 0
    correct = 0
    with torch.no_grad():
        for data in test_loader:
            data = data.to(device)
            output = model(data)
            loss = F.cross_entropy(output.transpose(-1,-2), data)
            
            test_loss += loss
            pred = output.argmax(dim=-1, keepdim=True)  # get the index of the max log-probability
            correct += pred.eq(data.view_as(pred)).sum().item() / 155
    
    test_loss /= len(test_loader)

    print('\nTest set: Average loss: {:.4f}, Accuracy: {}/{} ({:.0f}%)\n'.format(
        test_loss, correct, len(test_loader.dataset),
        100. * correct / len(test_loader.dataset)))

if __name__=="__main__":
    # Training settings
    use_cuda = True
    batch_size = 32
    lr = 1e-4
    gamma = 1.
    epochs = 100
    beta = 0.5
    beta_steps = 37400
    def scheduler():
        n_steps  = 0
        def schedule():
            nonlocal n_steps
            n_steps += 1

            if n_steps < 1000:

                return 0

            step = (n_steps-1000)/beta_steps
            step = min(1, step)

            return 0.5 * (1 + np.sin((step*np.pi)-(np.pi/2)))
        return schedule
    schedule = scheduler()
    device = torch.device("cuda" if use_cuda else "cpu")

    kwargs = {'num_workers': 1, 'pin_memory': True} if use_cuda else {}

    
    dataset = DX7Dataset()
    train_idxs, test_idxs = train_test_split(range(len(dataset)), random_state=42)
    train_dataset = DataSubset(dataset, train_idxs)
    test_dataset = DataSubset(dataset, test_idxs)

    train_loader = torch.utils.data.DataLoader(
        train_dataset,
        batch_size=batch_size, shuffle=True, **kwargs)
    test_loader = torch.utils.data.DataLoader(
        test_dataset,
        batch_size=batch_size, shuffle=True, **kwargs)

    model = Net().to(device)
    optimizer = optim.Adadelta(model.parameters(), lr=lr)

    scheduler = StepLR(optimizer, step_size=1, gamma=gamma)
    for epoch in range(1, epochs + 1):
        train(model, device, train_loader, optimizer, epoch)
        test(model, device, test_loader)
        # scheduler.step()

    # if args.save_model:
    #     torch.save(model.state_dict(), "mnist_cnn.pt")

    torch.save(model.state_dict(), ARTIFACTS_ROOT.joinpath('fm-param-vae-8.pt'))
# if __name__ == '__main__':
#     main()

# %%


# %%


# %%


# %%
