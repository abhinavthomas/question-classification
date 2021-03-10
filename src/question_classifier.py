# changes made to remove torch text
# All the configurations -> Need to be moved to config file in the script
import argparse
import configparser
import pickle
import random

import numpy as np
import torch
from sklearn.metrics import f1_score
from torch.utils.data.sampler import SubsetRandomSampler

from data.datamodel import QuestionDataset
from NN.classifiers import Classifier, Ensemble
from preprocess.categorical import LabelEncoder
from preprocess.text import VocabBuilder

SEED = 1
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
torch.manual_seed(SEED)
random.seed(SEED)

BATCH_SIZE = 32
N_EPOCHS = 50
EMBED_DIM = 200
HIDDEN_NODES = 50
lr = 1.5
STOP_FINE_TUNING = False
min_count = 3
use_bilstm = True
use_pre_emb = True
pre_emb_path = '../data/models/glove.small.txt'
train_path = "../data/dataset/train.txt"
test_path = "../data/dataset/test.txt"
text_vocab_path = '../data/dataset/text.vocab'
label_vocab_path = '../data/dataset/label.vocab'
model_path = '../data/models/model'
TEXT = None
LABEL = None
gamma = 0.9
lowercase = True
ensemble_size = 0


def train(model, question_tokens, seq_lengths):
    """
        Train the model
    """
    dataset = QuestionDataset(question_tokens, seq_lengths,
                              LABEL.build_labels(labels))

    # No. of unique tokens in text
    print("Size of TEXT vocabulary:", VOCAB_SIZE)

    # No. of unique tokens in label
    print("Size of LABEL vocabulary:", NUM_CLASS)
    #######

    # Creating data indices for training and validation splits:
    dataset_size = len(dataset)
    indices = list(range(dataset_size))
    validation_split = .3
    split = int(np.floor(validation_split * dataset_size))
    np.random.seed(SEED)
    np.random.shuffle(indices)
    train_indices, val_indices = indices[split:], indices[:split]

    # Creating PT data samplers and loaders:
    train_sampler = SubsetRandomSampler(train_indices)
    validation_sampler = SubsetRandomSampler(val_indices)
    # Create batche generator
    train_gen = torch.utils.data.DataLoader(
        dataset, batch_size=BATCH_SIZE, sampler=train_sampler)
    valid_gen = torch.utils.data.DataLoader(
        dataset, batch_size=BATCH_SIZE, sampler=validation_sampler)
    # Architecture of the model
    print(model)
    print("--------For LR: ", lr, " and batch size: ", BATCH_SIZE, "------------")
    # Train the model
    max_acc = model.fit(train_gen, valid_gen, N_EPOCHS, model_path)
    print(f"Model with validation accuracy: {max_acc * 100:.1f}% was saved")


def test(model):
    print('Checking the results of test dataset...')
    x_test = []
    y_test = []
    with open(test_path) as fp:
        test_text = fp.readlines()

    for line in test_text:
        label, text = line.split(' ', 1)
        x_test.append(text)
        y_test.append(label)

    x_test = TEXT.convert_sentences_to_encoding(x_test)
    y_test = np.array(LABEL.convert_labels_to_encodings(y_test))
    y_pred = model.predict(x_test)

    with open("../data/output/output.txt", 'w') as fp:
        fp.writelines(LABEL.convert_encodings_to_labels(y_pred))

    test_acc = (y_pred == y_test).sum().item()/len(y_test)
    score = f1_score(y_test, y_pred, average='micro')
    perf_metrics = [
        f'\tAccuracy: {test_acc * 100:.1f}', f'\F1-Score: {score:.3f}']
    with open("../data/output/output.txt", 'w') as fp:
        fp.writelines(LABEL.convert_encodings_to_labels(y_pred))
        fp.writelines(perf_metrics)
    print(perf_metrics)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-config', type=str, required=True,
                        help='Configuration file')
    parser.add_argument('--train', action='store_true',
                        help='Training mode - model is saved')
    parser.add_argument('--test', action='store_true',
                        help='Testing mode - needs a model to load')
    args = parser.parse_args()
    config = configparser.ConfigParser()
    config.sections()
    config.read(args.config)
    print(config.keys())

    train_path = config["path_train"]
    test_path = config["path_test"]
    name = config["model"]
    model_path = config["path_model"]
    pre_emb_path = config["path_pre_emb"]

    BATCH_SIZE = config["batch_size"]
    N_EPOCHS = config["epoch"]
    EMBED_DIM = config["word_embedding_dim"]
    HIDDEN_NODES = config["hidden_dim"]
    lr = config["lr_param"]
    STOP_FINE_TUNING = config["freeze"]
    min_count = config["minimum_word_freq"]
    use_bilstm = config["use_bilstm"]
    use_pre_emb = config["use_pre_emb"]
    ensemble_size = config["ensemble_size"]

    if args.train:
        # call train function
        with open(train_path) as fp:
            sents = fp.readlines()
        data_set = np.array(list(map(lambda x: x.split(' ', 1), sents)))
        questions, labels = data_set[:, 1], data_set[:, 0].tolist()
        TEXT = VocabBuilder(lowercase)
        LABEL = LabelEncoder()
        question_tokens, seq_lengths = TEXT.build_vocab(
            questions, min_freq=3, emb_file=pre_emb_path)

        VOCAB_SIZE = len(TEXT.itos)
        NUM_CLASS = len(set(LABEL.itol))
        if ensemble_size:
            model_list = [Classifier(VOCAB_SIZE, EMBED_DIM, NUM_CLASS, HIDDEN_NODES, use_bilstm=use_bilstm, use_pre_emb=use_pre_emb,
                                     pre_emb=TEXT.itov if use_pre_emb else None, freeze=STOP_FINE_TUNING, lr=lr, gamma=gamma, device=device).to(device) for i in range(ensemble_size)]
            model = Ensemble(model_list, device)
        else:
            model = Classifier(VOCAB_SIZE, EMBED_DIM, NUM_CLASS, HIDDEN_NODES, use_bilstm=use_bilstm, use_pre_emb=use_pre_emb,
                               pre_emb=TEXT.itov if use_pre_emb else None, freeze=STOP_FINE_TUNING, lr=lr, gamma=gamma, device=device).to(device)

        train(model, question_tokens, seq_lengths)

    elif args.test:
        with open(text_vocab_path, 'rb') as fp:
            TEXT = pickle.load(fp)

        with open(label_vocab_path, 'rb') as fp:
            LABEL = pickle.load(fp)

        VOCAB_SIZE = len(TEXT.itos)
        NUM_CLASS = len(set(LABEL.itol))
        model = Classifier(VOCAB_SIZE, EMBED_DIM, NUM_CLASS, HIDDEN_NODES, use_bilstm=use_bilstm, use_pre_emb=use_pre_emb,
                           pre_emb=TEXT.itov if use_pre_emb else None, freeze=STOP_FINE_TUNING, lr=lr, gamma=gamma, device=device).to(device)
        model.load_state_dict(torch.load(model_path))
        model.to(device)
        test(model)
