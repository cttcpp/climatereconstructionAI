import h5py
import torch
import netCDF4
import numpy as np
import pandas as pd
import imageio
import matplotlib.pyplot as plt

from dateutil import parser
from netCDF4 import Dataset
from fpdf import FPDF
from cdo import *
from torchvision.utils import make_grid, save_image
import config as cfg


def create_snapshot_image(model, dataset, filename, lstm_steps):
    image, mask, gt = zip(*[dataset[i] for i in range(8)])

    image = torch.stack(image).to(cfg.device)
    mask = torch.stack(mask).to(cfg.device)
    gt = torch.stack(gt).to(cfg.device)
    with torch.no_grad():
        output = model(image.to(cfg.device), mask.to(cfg.device)).to(cfg.device)

    image = image[:, lstm_steps, :, :, :]
    gt = gt[:, lstm_steps, :, :, :]
    mask = mask[:, lstm_steps, :, :, :]
    output = output[:, lstm_steps, :, :, :]

    # get only first channel
    image = torch.unsqueeze(image[:, 0, :, :], dim=1)
    gt = torch.unsqueeze(gt[:, 0, :, :], dim=1)
    mask = torch.unsqueeze(mask[:, 0, :, :], dim=1)

    output_comp = mask * image + (1 - mask) * output
    grid = make_grid(
        torch.cat(((image), mask, (output),
                   (output_comp), (gt)), dim=0))
    save_image(grid, filename)


def get_data(file, var):
    data = Dataset(file)
    time = data.variables['time']
    variable = data.variables[var]
    return variable, time


def plot_data(file, start=0, end=None, label='', var='pr'):
    data, time = get_data(file=file, var=var)
    if not end:
        end = time.__len__()
    plt.plot(time[start:end], np.squeeze(data)[start:end], label=label)
    plt.xlabel(time.units)
    plt.ylabel(data.units)
    plt.legend()


class PConvLSTMEvaluator:
    def __init__(self, eval_save_dir, mask_dir, test_dir, variable):
        self.eval_save_dir = eval_save_dir
        self.mask_dir = mask_dir
        self.test_dir = test_dir
        self.variable = variable

    def infill(self, model, dataset, partitions):
        """if not os.path.exists(self.eval_save_dir):
            os.makedirs('{:s}'.format(self.eval_save_dir))
        image = []
        mask = []
        gt = []
        output = []
        mid_index = None

        if partitions > dataset.__len__():
            partitions = dataset.__len__()
        if dataset.__len__() % partitions != 0:
            print("WARNING: The size of the dataset should be dividable by the number of partitions. The last "
                  + str(dataset.__len__() % partitions) + " time steps will not be infilled.")
        for split in range(partitions):
            image_part, mask_part, gt_part = zip(
                *[dataset[i + split * (dataset.__len__() // partitions)] for i in
                  range(dataset.__len__() // partitions)])
            image_part = torch.stack(image_part)
            mask_part = torch.stack(mask_part)
            gt_part = torch.stack(gt_part)
            # get results from trained network
            with torch.no_grad():
                output_part = model(image_part.to(cfg.device), mask_part.to(cfg.device))

            lstm_steps = output_part.shape[1] - 1

            image_part = image_part[:, lstm_steps, :, :, :].to(torch.device('cpu'))
            mask_part = mask_part[:, lstm_steps, :, :, :].to(torch.device('cpu'))
            gt_part = gt_part[:, lstm_steps, :, :, :].to(torch.device('cpu'))
            output_part = output_part[:, lstm_steps, :, :, :].to(torch.device('cpu'))

            # only select first channel
            image_part = torch.unsqueeze(image_part[:, 0, :, :], dim=1)
            gt_part = torch.unsqueeze(gt_part[:, 0, :, :], dim=1)
            mask_part = torch.unsqueeze(mask_part[:, 0, :, :], dim=1)

            image.append(image_part)
            mask.append(mask_part)
            gt.append(gt_part)
            output.append(output_part)

        image = torch.cat(image)
        mask = torch.cat(mask)
        gt = torch.cat(gt)
        output = torch.cat(output)

        # create output_comp
        output_comp = mask * image + (1 - mask) * output

        cvar = [image, mask, output, output_comp, gt]
        cname = ['image', 'mask', 'output', 'output_comp', 'gt']
        dname = ['time', 'lat', 'lon']
        for x in range(0, 5):
            h5 = h5py.File('%s' % (self.eval_save_dir + cname[x]), 'w')
            h5.create_dataset(self.variable, data=cvar[x].to(torch.device('cpu')))
            for dim in range(0, 3):
                h5[self.variable].dims[dim].label = dname[dim]
            h5.close()
        print("Infilled images saved!")"""
        # convert to netCDF files
        self.convert_h5_to_netcdf(True, 'image')
        self.convert_h5_to_netcdf(False, 'gt')
        self.convert_h5_to_netcdf(False, 'output')
        self.convert_h5_to_netcdf(False, 'output_comp')

    def create_evaluation_images(self, file, create_video=False, start_date=None, end_date=None):
        if not os.path.exists(self.eval_save_dir + 'images'):
            os.makedirs('{:s}'.format(self.eval_save_dir + 'images'))

        data = Dataset(self.eval_save_dir + file)
        time = data.variables['time']
        time = netCDF4.num2date(time[:], time.units)

        if start_date and end_date:
            start = parser.parse(start_date)
            end = parser.parse(end_date)
            pr = [data.variables[self.variable][i, :, :] for i in range(time.__len__()) if
                  time[i] >= start and time[i] <= end]
            time = [time[i] for i in range(time.__len__()) if time[i] >= start and time[i] <= end]
        else:
            pr = data.variables[self.variable][:, :, :]

        for i in range(time.__len__()):
            plt.imshow(np.squeeze(pr[i]), vmin=0, vmax=5)
            plt.axis('off')
            plt.title('Precipitation from ' + str(time[i]))
            plt.savefig(self.eval_save_dir + 'images/' + file + '_' + str(i) + '.jpg')
            plt.clf()

        if create_video:
            with imageio.get_writer(self.eval_save_dir + 'images/' + file + '_movie.gif', mode='I') as writer:
                for i in range(time.__len__()):
                    image = imageio.imread(self.eval_save_dir + 'images/' + file + '_' + str(i) + '.jpg')
                    writer.append_data(image)

    def create_evaluation_report(self, save_dir='evaluations/', create_evalutation_files=True, clean_data=True,
                                 infilled=True):
        if not os.path.exists(self.eval_save_dir + save_dir):
            os.makedirs('{:s}'.format(self.eval_save_dir + save_dir))
        directory = self.eval_save_dir + save_dir
        if create_evalutation_files:
            self.create_evaluation_files(clean_data, infilled, directory)

        mse, _ = get_data(file=directory + 'mse.nc', var=self.variable)
        mse = mse[0][0][0]

        timcor, _ = get_data(file=directory + 'timcor.nc', var=self.variable)
        timcor = timcor[0][0][0]

        total_pr_gt, _ = get_data(file=directory + 'fldsum_gt.nc', var=self.variable)
        total_pr_gt = total_pr_gt[0][0][0]

        total_pr_output_comp, _ = get_data(file=directory + 'fldsum_output_comp.nc', var=self.variable)
        total_pr_output_comp = total_pr_output_comp[0][0][0]

        mean_fldcor, _ = get_data(file=directory + 'gtVSout_fldcor_timmean.nc', var=self.variable)
        mean_fldcor = mean_fldcor[0][0][0]

        timsum_fldcor, _ = get_data(file=directory + 'gtVSout_fldcor_timsum.nc', var=self.variable)
        timsum_fldcor = timsum_fldcor[0][0][0]

        plt.title('Max values')
        plot_data(file=directory + 'gt_max.nc', start=0, label='Ground Truth', var=self.variable)
        plot_data(file=directory + 'output_comp_max.nc', start=0, label='Output', var=self.variable)
        plt.savefig(directory + 'max.png')
        plt.clf()

        plt.title('Min values')
        plot_data(file=directory + 'gt_min.nc', start=0, label='Ground Truth', var=self.variable)
        plot_data(file=directory + 'output_comp_min.nc', start=0, label='Output', var=self.variable)
        plt.savefig(directory + 'min.png')

        plt.clf()
        plt.title('Mean values')
        plot_data(file=directory + 'gt_mean.nc', label='Ground Truth', var=self.variable)
        plot_data(file=directory + 'output_comp_mean.nc', label='Output', var=self.variable)
        plt.savefig(directory + 'mean.png')

        plt.clf()
        plt.title('Field Correlation')
        plot_data(file=directory + 'gtVSout_fldcor.nc', label='Field correlation GT vs Output', var=self.variable)
        plt.savefig(directory + 'fldcor.png')

        df = pd.DataFrame()
        df['Statistical Value'] = ["MSE", "Time Correlation", "Total Precipitation", "Other"]
        df['Ground Truth'] = ['%.5f' % mse, '%.5f' % timcor, total_pr_gt, 'Mean fldcor:' + str('%.5f' % mean_fldcor)]
        df['Output'] = ['%.5f' % mse, '%.5f' % timcor, total_pr_output_comp, 'Tim Sum:' + str('%.5f' % timsum_fldcor)]

        pdf = FPDF()
        pdf.add_page()
        pdf.set_xy(0, 0)
        pdf.set_font('arial', 'B', 12)
        pdf.cell(60)
        pdf.cell(75, 10, "Statistical evaluation of Ground Truth and Output Comp", 0, 2, 'C')
        pdf.cell(90, 10, " ", 0, 2, 'C')
        pdf.cell(-40)
        pdf.cell(50, 10, 'Statistical Value', 1, 0, 'C')
        pdf.cell(40, 10, 'Ground Truth', 1, 0, 'C')
        pdf.cell(40, 10, 'Output', 1, 2, 'C')
        pdf.cell(-90)
        pdf.set_font('arial', '', 12)
        for i in range(0, len(df)):
            pdf.cell(50, 10, '%s' % (df['Statistical Value'].iloc[i]), 1, 0, 'C')
            pdf.cell(40, 10, '%s' % (str(df['Ground Truth'].iloc[i])), 1, 0, 'C')
            pdf.cell(40, 10, '%s' % (str(df['Output'].iloc[i])), 1, 2, 'C')
            pdf.cell(-90)
        pdf.cell(90, 10, " ", 0, 2, 'C')
        pdf.cell(-30)
        pdf.image(directory + 'max.png', x=None, y=None, w=0, h=0, type='', link='')
        pdf.image(directory + 'min.png', x=None, y=None, w=0, h=0, type='', link='')
        pdf.image(directory + 'mean.png', x=None, y=None, w=0, h=0, type='', link='')
        pdf.image(directory + 'fldcor.png', x=None, y=None, w=0, h=0, type='', link='')
        pdf.output(directory + 'Report.pdf', 'F')

    def evaluate_selected_samples(self, dates=None):
        cdo = Cdo()
        if dates is None:
            dates = ['2017-01-12T23', '2017-04-17T15', '2017-05-02T12', '2017-05-13T12', '2017-06-04T03',
                     '2017-06-29T16', '2017-07-12T14', '2017-09-02T13']
        i = 0
        for date in dates:
            cdo.select('date=' + date, input=self.eval_save_dir + 'image.nc',
                       output=self.eval_save_dir + 'imagetmp' + str(i) + '.nc')
            cdo.select('date=' + date, input=self.eval_save_dir + 'output_comp.nc',
                       output=self.eval_save_dir + 'output_comptmp' + str(i) + '.nc')
            cdo.select('date=' + date, input=self.eval_save_dir + 'gt.nc',
                       output=self.eval_save_dir + 'gttmp' + str(i) + '.nc')
        cdo.mergetime(input=self.eval_save_dir + 'imagetmp*', output=self.eval_save_dir + 'image_selected.nc')
        cdo.mergetime(input=self.eval_save_dir + 'output_comptmp*',
                      output=self.eval_save_dir + 'output_comp_selected.nc')
        cdo.mergetime(input=self.eval_save_dir + 'gttmp*', output=self.eval_save_dir + 'gt_selected.nc')
        os.system('rm ' + self.eval_save_dir + '*tmp*')

        self.create_evaluation_images(file='image_selected.nc')
        self.create_evaluation_images(file='gt_selected.nc')
        self.create_evaluation_images(file='output_comp_selected.nc')

    def create_evaluation_files(self, clean_data, infilled, save_dir):
        cdo = Cdo()
        output_comp = 'output_comp.nc'
        gt = 'gt.nc'
        if clean_data:
            cdo.gec(0.0, input=self.eval_save_dir + 'output_comp.nc', output=self.eval_save_dir + 'tmp.nc')
            cdo.mul(input=self.eval_save_dir + 'output_comp.nc ' + self.eval_save_dir + 'tmp.nc',
                    output=self.eval_save_dir + 'output_comp_cleaned.nc')
            os.system('rm ' + self.eval_save_dir + 'tmp.nc')
            output_comp = 'output_comp_cleaned.nc'
        if infilled:
            cdo.ifnotthen(input=self.mask_dir + ' ' + self.eval_save_dir + output_comp,
                          output=self.eval_save_dir + 'infilled_output_comp.nc')
            output_comp = 'infilled_output_comp.nc'
            cdo.ifnotthen(input=self.mask_dir + ' ' + self.eval_save_dir + gt,
                          output=self.eval_save_dir + 'infilled_gt.nc')
            gt = 'infilled_gt.nc'

        # create correlation
        cdo.timcor(
            input='-hourmean -fldmean ' + self.eval_save_dir + output_comp + ' -hourmean -fldmean ' + self.eval_save_dir + gt,
            output=save_dir + 'timcor.nc')
        # create sum in field
        cdo.timcor(
            input='-hourmean -fldsum ' + self.eval_save_dir + output_comp + ' -hourmean -fldsum ' + self.eval_save_dir + gt,
            output=save_dir + 'fldsum_timcor.nc')
        # create mse
        cdo.sqrt(
            input='-timmean -sqr -sub -hourmean -fldmean ' + self.eval_save_dir + output_comp + ' -hourmean -fldmean ' + self.eval_save_dir + gt,
            output=save_dir + 'mse.nc')
        # create total fldsum
        cdo.fldsum(input='-timsum ' + self.eval_save_dir + output_comp, output=save_dir + 'fldsum_output_comp.nc')
        cdo.fldsum(input='-timsum ' + self.eval_save_dir + gt, output=save_dir + 'fldsum_gt.nc')
        # create timeseries of field correlation and mean
        cdo.fldcor(
            input='-setmissval,1e20 ' + self.eval_save_dir + output_comp + ' -setmissval,1e20 ' + self.eval_save_dir + gt,
            output=save_dir + 'gtVSout_fldcor.nc')
        cdo.timmean(
            input='-fldcor -setmissval,1e20 ' + self.eval_save_dir + output_comp + ' -setmissval,1e20 ' + self.eval_save_dir + gt,
            output=save_dir + 'gtVSout_fldcor_timmean.nc')
        # create fldcor over year sum
        cdo.fldcor(
            input='-timsum -setmissval,1e20 ' + self.eval_save_dir + output_comp + ' -timsum -setmissval,1e20 ' + self.eval_save_dir + gt,
            output=save_dir + 'gtVSout_fldcor_timsum.nc')

        # create min max mean time series
        cdo.fldmax(input=self.eval_save_dir + output_comp, output=save_dir + 'output_comp_max.nc')
        cdo.fldmax(input=self.eval_save_dir + gt, output=save_dir + 'gt_max.nc')
        cdo.fldmin(input=self.eval_save_dir + output_comp, output=save_dir + 'output_comp_min.nc')
        cdo.fldmin(input=self.eval_save_dir + gt, output=save_dir + 'gt_min.nc')
        cdo.fldmean(input=self.eval_save_dir + output_comp, output=save_dir + 'output_comp_mean.nc')
        cdo.fldmean(input=self.eval_save_dir + gt, output=save_dir + 'gt_mean.nc')

    def convert_h5_to_netcdf(self, create_structure_template, file):
        if create_structure_template:
            os.system('ncdump ' + self.test_dir + '*.h5 > ' + self.eval_save_dir + 'tmp_dump.txt')
            os.system(
                'sed "/.*' + self.variable + ' =.*/{s///;q;}" ' + self.eval_save_dir + 'tmp_dump.txt > ' + self.eval_save_dir + 'structure.txt')
            os.system('rm ' + self.eval_save_dir + 'tmp_dump.txt')
        cdo = Cdo()
        os.system('cat ' + self.eval_save_dir + 'structure.txt >> ' + self.eval_save_dir + file + '.txt')
        os.system(
            'ncdump -v ' + self.variable + ' ' + self.eval_save_dir + file + ' | sed -e "1,/data:/d" >> ' + self.eval_save_dir + file + '.txt')
        os.system('ncgen -o ' + self.eval_save_dir + 'output-tmp ' + self.eval_save_dir + file + '.txt')
        cdo.setgrid(self.test_dir + '*.h5', input=self.eval_save_dir + 'output-tmp',
                    output=self.eval_save_dir + file + '.nc')
        os.system('rm ' + self.eval_save_dir + file + '.txt ' + self.eval_save_dir + 'output-tmp')