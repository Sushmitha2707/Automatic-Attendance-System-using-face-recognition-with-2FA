import os
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import librosa
import numpy as np
from voice_recognition import VoiceNet

class VoiceDataset(Dataset):
    def __init__(self, data_dir):
        self.samples = []
        self.labels = []
        self.class_names = []
        
        print("Loading dataset from:", data_dir)
        
        for idx, person_id in enumerate(os.listdir(data_dir)):
            person_dir = os.path.join(data_dir, person_id)
            self.class_names.append(person_id)
            
            if os.path.isdir(person_dir):
                for audio_file in os.listdir(person_dir):
                    if audio_file.endswith('.wav'):
                        try:
                            # Validate audio file before adding
                            y, sr = librosa.load(os.path.join(person_dir, audio_file))
                            if len(y) > 0:  # Check if audio data is valid
                                self.samples.append(os.path.join(person_dir, audio_file))
                                self.labels.append(idx)
                                print(f"Added sample: {audio_file} for {person_id}")
                        except Exception as e:
                            print(f"Skipping invalid audio file: {audio_file}")
    
    def __len__(self):
        return len(self.samples)
    
    def __getitem__(self, idx):
        audio_path = self.samples[idx]
        try:
            # Fixed duration and parameters
            y, sr = librosa.load(audio_path, duration=3.0, sr=22050)
            if len(y) < sr * 3:
                y = np.pad(y, (0, sr * 3 - len(y)))
            
            # Fixed size mel spectrogram
            mel_spect = librosa.feature.melspectrogram(
                y=y, 
                sr=sr,
                n_mels=64,
                n_fft=2048,
                hop_length=512
            )
            mel_spect_db = librosa.power_to_db(mel_spect, ref=np.max)
            mel_spect_db = (mel_spect_db - mel_spect_db.min()) / (mel_spect_db.max() - mel_spect_db.min())
            
            # Ensure fixed size output
            target_length = 130  # Fixed length for all spectrograms
            if mel_spect_db.shape[1] > target_length:
                mel_spect_db = mel_spect_db[:, :target_length]
            else:
                pad_width = target_length - mel_spect_db.shape[1]
                mel_spect_db = np.pad(mel_spect_db, ((0, 0), (0, pad_width)))
            
            return torch.FloatTensor(mel_spect_db).unsqueeze(0), self.labels[idx]
        except Exception as e:
            print(f"Error processing {audio_path}: {e}")
            # Return zero tensor with correct dimensions
            return torch.zeros((1, 64, 130)), self.labels[idx]

def train_model():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")
    
    # Load dataset with smaller batch size and drop_last=True
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'voice_samples')
    dataset = VoiceDataset(data_dir)
    
    if len(dataset) == 0:
        print("No valid samples found!")
        return
        
    print(f"Total samples: {len(dataset)}")
    print(f"Number of classes: {len(dataset.class_names)}")
    
    dataloader = DataLoader(
        dataset, 
        batch_size=8,  # Smaller batch size
        shuffle=True,
        drop_last=True  # Drop incomplete batches
    )
    
    # Initialize model
    model = VoiceNet(len(dataset.class_names)).to(device)
    model.class_names = dataset.class_names
    
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=0.001)
    
    # Training loop
    num_epochs = 50
    for epoch in range(num_epochs):
        model.train()
        running_loss = 0.0
        correct = 0
        total = 0
        
        for inputs, labels in dataloader:
            inputs, labels = inputs.to(device), labels.to(device)
            
            optimizer.zero_grad()
            outputs = model(inputs)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
            
            running_loss += loss.item()
            _, predicted = torch.max(outputs.data, 1)
            total += labels.size(0)
            correct += (predicted == labels).sum().item()
        
        epoch_loss = running_loss / len(dataloader)
        accuracy = 100 * correct / total
        print(f'Epoch [{epoch+1}/{num_epochs}], Loss: {epoch_loss:.4f}, Accuracy: {accuracy:.2f}%')
    
    # Save model (in training script)
    model_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'models', 'voice_model.pth')
    torch.save({
        'model_state_dict': model.state_dict(),
        'class_names': model.class_names
    }, model_path)
    print(f"\nModel saved to {model_path}")

if __name__ == "__main__":
    train_model()