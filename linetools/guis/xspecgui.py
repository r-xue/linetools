""" Module for XSpecGui
"""
from __future__ import print_function, absolute_import, division, unicode_literals

import sys
import numpy as np
import pdb

from PyQt5 import QtGui
from PyQt5.QtWidgets import QWidget, QLabel, QPushButton, QMainWindow
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout
from PyQt5 import QtCore

from matplotlib import rcParams

from astropy.units import Quantity
from astropy import units as u

from linetools.guis import utils as ltgu
from linetools.guis import line_widgets as ltgl
from linetools.guis import spec_widgets as ltgsp

from linetools import utils as ltu
from linetools.analysis import voigt as lav
from linetools.isgm.abscomponent import AbsComponent
from linetools.isgm import utils as ltiu


try:
    basestring
except NameError:  # For Python 3
    basestring = str

class XSpecGui(QMainWindow):
    """ GUI to replace XIDL x_specplot (which simulated a GUI by T. Barlow)
    """
    def __init__(self, ispec, guessfile=None, parent=None, zsys=None, norm=None, exten=None,
                 rsp_kwargs={}, unit_test=False, screen_scale=1.,
                 **kwargs):
        QMainWindow.__init__(self, parent)
        """
        ispec = str, XSpectrum1D or tuple of arrays
          Input spectrum or spectrum filename.  If tuple then (wave,
          fx), (wave, fx, sig) or (wave, fx, sig, co)
        guessfile : str, optional
          name of the .json file generated with igmguesses
          if not None - overplot fitted line profiles from igmguesses
        parent : Widget parent, optional
        zsys : float, optional
          intial redshift
        exten : int, optional
          extension for the spectrum in multi-extension FITS file
        norm : bool, optional
          True if the spectrum is normalized
        screen_scale : float, optional
          Scale the default sizes for the gui size
        """
        #reload(ltgl)
        #reload(ltgsp)
        # INIT
        #QtCore.pyqtRemoveInputHook()
        #xdb.set_trace()
        #QtCore.pyqtRestoreInputHook()

        self.scale = screen_scale

        # Needed to avoid crash in large spectral files
        rcParams['agg.path.chunksize'] = 20000
        rcParams['axes.formatter.useoffset'] = False  # avoid scientific notation in axes tick labels

        # Build a widget combining several others
        self.main_widget = QWidget()

        # Status bar
        self.create_status_bar()

        # Grab the pieces and tie together
        self.pltline_widg = ltgl.PlotLinesWidget(status=self.statusBar,
            init_z=zsys, screen_scale=self.scale)
        self.pltline_widg.setMaximumWidth(300*self.scale)


        ## Abs sys
        abs_sys = None
        voigtsfit = None
        if guessfile is not None:
            # Load
            igm_guess = ltu.loadjson(guessfile)
            comps = []
            for key in igm_guess['cmps'].keys():
                comp = AbsComponent.from_dict(igm_guess['cmps'][key], chk_vel=False)
                comps.append(comp)
            abs_sys = ltiu.build_systems_from_components(comps,
                                                         vsys=500. * u.km / u.s)  # ,chk_z=False)  ### 100000.*u.km/u.s   ok

            ### voigt fit - added
            # Spectrum
            spec, spec_fil = ltgu.read_spec(ispec, exten=exten, norm=norm,
                                            rsp_kwargs=rsp_kwargs)

            voigts = np.asarray([0] * len(spec.wavelength))
            for iabs_sys in abs_sys:
                lines = iabs_sys.list_of_abslines()
                ###
                for iline in lines:
                    if iline.analy['do_analysis'] == 0:
                        continue
                    if iline.attrib['b'] > 0:
                        lavfitline = lav.voigt_from_abslines(spec.wavelength, iline, fwhm=3.)
                        fitflux = lavfitline.flux.value
                        voigts = voigts + np.asarray([1] * len(voigts)) - fitflux
            voigts[np.where(voigts > 1)] = 1
            voigtsfit = np.asarray([1] * len(voigts)) - voigts

            if not norm:
                voigtsfit = voigtsfit * spec.co


        # Hook the spec widget to Plot Line
        self.spec_widg = ltgsp.ExamineSpecWidget(ispec,guessfile=guessfile,voigtsfit=voigtsfit,status=self.statusBar,
                                                 parent=self, llist=self.pltline_widg.llist,
                                                zsys=zsys, norm=norm, exten=exten, abs_sys=abs_sys,
                                                screen_scale=self.scale,
                                                 rsp_kwargs=rsp_kwargs, **kwargs)
        self.pltline_widg.spec_widg = self.spec_widg
        # Multi spec
        self.mspec_widg = ltgsp.MultiSpecWidget(self.spec_widg)


        self.spec_widg.canvas.mpl_connect('button_press_event', self.on_click)

        # Layout

        # Extras
        extras = QWidget()
        extras.setMaximumWidth(130*self.scale)
        vbox = QVBoxLayout()
        qbtn = QPushButton(self)
        qbtn.setText('Quit')
        qbtn.clicked.connect(self.quit)
        vbox.addWidget(self.pltline_widg)
        vbox.addWidget(self.mspec_widg)
        vbox.addWidget(qbtn)
        extras.setLayout(vbox)

        # Main window
        hbox = QHBoxLayout()
        hbox.addWidget(self.spec_widg)
        hbox.addWidget(extras)

        self.main_widget.setLayout(hbox)

        # Point MainWindow
        self.setCentralWidget(self.main_widget)
        if unit_test:
            self.quit()

    def create_status_bar(self):
        """ Status bar for the GUI
        """
        self.status_text = QLabel("XSpec")
        self.statusBar().addWidget(self.status_text, 1)

    def on_click(self, event):
        """ Over-loads click events
        """
        if event.button == 3: # Set redshift
            if event.xdata is None:  # Mac bug [I think]
                return
            if self.pltline_widg.llist['List'] is None:
                return
            self.select_line_widg = ltgl.SelectLineWidget(
                self.pltline_widg.llist[self.pltline_widg.llist['List']]._data,
                scale=self.scale)
            self.select_line_widg.exec_()
            line = self.select_line_widg.line
            if line.strip() == 'None':
                return
            #
            quant = line.split('::')[1].lstrip()
            spltw = quant.split(' ')
            #QtCore.pyqtRemoveInputHook()
            #pdb.set_trace()
            #QtCore.pyqtRestoreInputHook()
            wrest = Quantity(float(spltw[0]), unit=self.pltline_widg.llist[
                self.pltline_widg.llist['List']]._data['wrest'].unit) # spltw[1])  [A bit risky!]
            z = event.xdata/wrest.value - 1.
            self.pltline_widg.llist['z'] = z
            self.statusBar().showMessage('z = {:f}'.format(z))

            self.pltline_widg.zbox.setText('{:.5f}'.format(self.pltline_widg.llist['z']))

            # Draw
            self.spec_widg.on_draw()
    # Quit
    def quit(self):
        self.close()


def main(args, **kwargs):
    from PyQt5.QtWidgets import QApplication
    from linetools.spectra.xspectrum1d import XSpectrum1D

    if not isinstance(args,(XSpectrum1D,tuple,basestring)):
        raise IOError("Bad input")
    # Run
    app = QApplication(sys.argv)
    gui = XSpecGui(args, **kwargs)
    gui.show()
    app.exec_()
    return

