import numpy as np
import torch
import torch.nn as nn
from torch.autograd import Variable
from torch.utils.data import DataLoader
from torchvision import transforms
import torch.backends.cudnn as cudnn
import torchvision
import torch.nn.functional as F

import cv2
import matplotlib.pyplot as plt
import sys
import os
import argparse

import datasets
import hopenet
import utils

def parse_args():
    """Parse input arguments."""
    parser = argparse.ArgumentParser(description='Head pose estimation using the Hopenet network.')
    parser.add_argument('--gpu', dest='gpu_id', help='GPU device id to use [0]',
            default=0, type=int)
    parser.add_argument('--data_dir', dest='data_dir', help='Directory path for data.',
          default='', type=str)
    parser.add_argument('--filename_list', dest='filename_list', help='Path to text file containing relative paths for every example.',
          default='', type=str)
    parser.add_argument('--snapshot', dest='snapshot', help='Name of model snapshot.',
          default='', type=str)
    parser.add_argument('--batch_size', dest='batch_size', help='Batch size.',
          default=1, type=int)
    parser.add_argument('--save_viz', dest='save_viz', help='Save images with pose cube.',
          default=False, type=bool)

    args = parser.parse_args()

    return args

if __name__ == '__main__':
    args = parse_args()

    cudnn.enabled = True
    batch_size = 1
    gpu = args.gpu_id
    snapshot_path = os.path.join('output/snapshots', args.snapshot + '.pkl')

    # ResNet50 with 3 outputs.
    model = hopenet.Hopenet(torchvision.models.resnet.Bottleneck, [3, 4, 6, 3], 66)
    # model = hopenet.Hopenet(torchvision.models.resnet.BasicBlock, [2, 2, 2, 2], 66)

    print 'Loading snapshot.'
    # Load snapshot
    saved_state_dict = torch.load(snapshot_path)
    model.load_state_dict(saved_state_dict)

    print 'Loading data.'

    transformations = transforms.Compose([transforms.Scale(224),
    transforms.RandomCrop(224), transforms.ToTensor()])

    pose_dataset = datasets.AFLW2000_binned(args.data_dir, args.filename_list,
                                transformations)
    test_loader = torch.utils.data.DataLoader(dataset=pose_dataset,
                                               batch_size=batch_size,
                                               num_workers=2)

    model.cuda(gpu)

    print 'Ready to test network.'

    # Test the Model
    model.eval()  # Change model to 'eval' mode (BN uses moving mean/var).
    total = 0
    n_margins = 20
    yaw_correct = np.zeros(n_margins)
    pitch_correct = np.zeros(n_margins)
    roll_correct = np.zeros(n_margins)

    idx_tensor = [idx for idx in xrange(66)]
    idx_tensor = torch.FloatTensor(idx_tensor).cuda(gpu)

    yaw_error = .0
    pitch_error = .0
    roll_error = .0

    for i, (images, labels, name) in enumerate(test_loader):
        images = Variable(images).cuda(gpu)

        total += labels.size(0)
        label_yaw = labels[:,0]
        label_pitch = labels[:,1]
        label_roll = labels[:,2]

        yaw, pitch, roll = model(images)

        # Binned predictions
        _, yaw_bpred = torch.max(yaw.data, 1)
        _, pitch_bpred = torch.max(pitch.data, 1)
        _, roll_bpred = torch.max(roll.data, 1)

        yaw_predicted = F.softmax(yaw)
        pitch_predicted = F.softmax(pitch)
        roll_predicted = F.softmax(roll)

        # Continuous predictions
        yaw_predicted = torch.sum(yaw_predicted.data[0] * idx_tensor)
        pitch_predicted = torch.sum(pitch_predicted.data[0] * idx_tensor)
        roll_predicted = torch.sum(roll_predicted.data[0] * idx_tensor)

        # Mean absolute error
        yaw_error += abs(yaw_predicted - label_yaw[0]) * 3
        pitch_error += abs(pitch_predicted - label_pitch[0]) * 3
        roll_error += abs(roll_predicted - label_roll[0]) * 3

        # Binned Accuracy
        # for er in xrange(n_margins):
        #     yaw_bpred[er] += (label_yaw[0] in range(yaw_bpred[0,0] - er, yaw_bpred[0,0] + er + 1))
        #     pitch_bpred[er] += (label_pitch[0] in range(pitch_bpred[0,0] - er, pitch_bpred[0,0] + er + 1))
        #     roll_bpred[er] += (label_roll[0] in range(roll_bpred[0,0] - er, roll_bpred[0,0] + er + 1))

        # print label_yaw[0], yaw_bpred[0,0]

        # Save images with pose cube.
        if args.save_viz:
            name = name[0]
            cv2_img = cv2.imread(os.path.join(args.data_dir, name + '.jpg'))
            #cv2_img = cv2.cvtColor(cv2_img, cv2.COLOR_RGB2BGR)
            #print name
            #print label_yaw[0] * 3 - 99, label_pitch[0] * 3 - 99, label_roll[0] * 3 - 99
            #print yaw_predicted * 3 - 99, pitch_predicted * 3 - 99, roll_predicted * 3 - 99
            utils.plot_pose_cube(cv2_img, yaw_predicted * 3 - 99, pitch_predicted * 3 - 99, roll_predicted * 3 - 99)
            cv2.imwrite(os.path.join('output/images', name + '.jpg'), cv2_img)

    print('Test error in degrees of the model on the ' + str(total) +
    ' test images. Yaw: %.4f, Pitch: %.4f, Roll: %.4f' % (yaw_error / total,
    pitch_error / total, roll_error / total))

    # Binned accuracy
    # for idx in xrange(len(yaw_correct)):
    #     print yaw_correct[idx] / total, pitch_correct[idx] / total, roll_correct[idx] / total