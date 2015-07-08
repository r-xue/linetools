"""
Module for utilites related to spectra
  -- Main item is a Class XSpectrum1D which overloads Spectrum1D
"""
from __future__ import print_function, absolute_import, division, unicode_literals

import numpy as np
import os

import astropy as apy
from astropy import units as u
from astropy import constants as const
from astropy.io import fits
from astropy.nddata import StdDevUncertainty

from specutils import Spectrum1D
from specutils.wcs.specwcs import Spectrum1DPolynomialWCS, Spectrum1DLookupWCS

#from xastropy.xutils import xdebug as xdb

# Child Class of specutils/Spectrum1D
#    Generated by JXP to add functionality before it gets ingested in the specutils distribution
class XSpectrum1D(Spectrum1D):
    '''Class to over-load Spectrum1D for new functionality not yet in specutils
    '''

    #### ###############################
    #  Instantiate from Spectrum1D 
    @classmethod
    def from_spec1d(cls, spec1d):

        # Giddy up
        return cls(flux=spec1d.flux, wcs=spec1d.wcs, unit=spec1d.unit,
                   uncertainty=spec1d.uncertainty, mask=spec1d.mask, meta=spec1d.meta)

    @property
    def sig(self):
        ''' Return a standard 1sigma error array
        '''
        if isinstance(self.uncertainty,StdDevUncertainty):
            return self.uncertainty.array
        else:
            return None


    #  Add noise
    def add_noise(self,seed=None,s2n=None):
        '''Add noise to the existing spectrum
        Uses the uncertainty array unless otherwise specified
        Converts flux to float64

        Parameters:
        -----------
        seed: int, optional  
          Seed for the random number generator [not yet functional]
        s2n: float, optional
          S/N per pixel for the output spectrum
        '''
        # Seed
        np.random.seed(seed=seed)
        #
        npix = len(self.flux)
        # Random numbers
        rand = np.random.normal(size=npix)

        # Modifty the flux
        if s2n is not None:
            sig =  1./s2n
        else:
            sig = self.sig
        #
        self.flux = self.flux.value + (rand * sig)*self.flux.unit

    #  Normalize
    def normalize(self, conti, verbose=False, no_check=False):
        """
        Normalize the spectrum with an input continuum

        Parameters
        ----------
        conti: numpy array
          Continuum
        verbose: bool, optional (False)
        no_check: bool, optional (False)
          Check size of array?
        """
        # Sanity check
        if (len(conti) != len(self.flux)): 
            if no_check:
                print('WARNING: Continuum length differs from flux')
                if len(conti) > len(self.flux):
                    self.flux = self.flux / conti[0:len(self.flux)]
                    return
                else:
                    raise ValueError('normalize: Continuum needs to be longer!')
            else:
                raise ValueError('normalize: Continuum needs to be same length as flux array')

        # Adjust the flux
        self.flux = self.flux / conti
        if verbose:
            print('spec.utils: Normalizing the spectrum')


    #### ###############################
    #  Grabs spectrum pixels in a velocity window
    def pix_minmax(self, *args):
        """Find pixels in velocity range

        Parameters
        ----------
        Option 1: wvmnx
          wvmnx: Tuple of 2 floats
            wvmin, wvmax in spectral units

        Option 2: zabs, wrest, vmnx  [not as a tuple or list!]
          zabs: Absorption redshift
          wrest: Rest wavelength  (with Units!)
          vmnx: Tuple of 2 floats
            vmin, vmax in km/s

        Returns:
        ----------
        pix: array
          Integer list of pixels
        """
        if len(args) == 1: # Option 1
            wvmnx = args[0]
        elif len(args) == 3: # Option 2
            from astropy import constants as const
            # args = zabs, wrest, vmnx
            wvmnx = (args[0]+1) * (args[1] + (args[1] * args[2] / const.c.to('km/s')) )
            wvmnx.to(u.AA)

        # Locate the values
        pixmin = np.argmin( np.fabs( self.dispersion-wvmnx[0] ) )
        pixmax = np.argmin( np.fabs( self.dispersion-wvmnx[1] ) )

        gdpix = np.arange(pixmin,pixmax+1)

        # Fill + Return
        self.sub_pix = gdpix
        return gdpix, wvmnx, (pixmin, pixmax)

    #### ###############################


    # Splice spectrum + Normalize
    def parse_spec(spec, **kwargs):
        ''' Slice the spectrum.
        Normalize too
        '''
        fx = spec.flux[spec.sub_pix]
        sig = spec.sig[spec.sub_pix] 

        # Normalize?
        try:
            conti = kwargs['conti']
        except KeyError:
            pass
        else:
            if len(conti) != len(spec.flux): # Check length
                raise ValueError('lines_utils.aodm: Continuum length must match input spectrum')
            fx = fx / conti[spec.sub_pix]
            sig = sig / conti[spec.sub_pix]

        return fx, sig


    # Quick plot
    def plot(self):
        ''' Plot the spectrum

        Parameters
        ----------
        '''
        import matplotlib.pyplot as plt

        if self.sig is not None:
            plt.plot(self.dispersion, self.flux)
            plt.plot(self.dispersion, self.sig)
        else:
            plt.plot(self.dispersion, self.flux)
        plt.show()

    #  Rebin
    def rebin(self, new_wv):
        """ Rebin the existing spectrum rebinned to a new wavelength array
        Uses simple linear interpolation.  The default (and only) option 
        conserves counts (and flambda).
        
        WARNING: Do not trust either edge pixel of the new array

        Parameters
        ----------
        new_wv: Quantity array
          New wavelength array

        Returns:
        ----------
          XSpectrum1D of the rebinned spectrum
        """
        from scipy.interpolate import interp1d

        # Endpoints of original pixels
        npix = len(self.dispersion)
        wvh = (self.dispersion + np.roll(self.dispersion, -1))/2.
        wvh[npix-1] = self.dispersion[npix-1] + (self.dispersion[npix-1] - self.dispersion[npix-2])/2.
        dwv = wvh - np.roll(wvh,1)
        dwv[0] = 2*(wvh[0]-self.dispersion[0])

        # Cumulative Sum
        cumsum = np.cumsum(self.flux * dwv)

        # Interpolate (loses the units)
        fcum = interp1d(wvh, cumsum, fill_value=0., bounds_error=False)

        # Endpoints of new pixels
        nnew = len(new_wv)
        nwvh = (new_wv + np.roll(new_wv, -1))/2.
        nwvh[nnew-1] = new_wv[nnew-1] + (new_wv[nnew-1] - new_wv[nnew-2])/2.
        # Pad starting point
        bwv = np.zeros(nnew+1) * new_wv.unit
        bwv[0] = new_wv[0] - (new_wv[1] - new_wv[0])/2.
        bwv[1:] = nwvh

        # Evaluate and put unit back
        newcum = fcum(bwv) * dwv.unit

        # Endpoint
        if (bwv[-1] > wvh[-1]):
            newcum[-1] = cumsum[-1]

        # Rebinned flux
        new_fx = (np.roll(newcum,-1)-newcum)[:-1]

        # Normalize (preserve counts and flambda)
        new_dwv = bwv - np.roll(bwv,1)
        #import pdb
        #pdb.set_trace()
        new_fx = new_fx / new_dwv[1:]

        # Return new spectrum
        return XSpectrum1D.from_array(new_wv, new_fx)

    # Velo array
    def relative_vel(self, wv_obs):
        ''' Return a velocity array relative to an input wavelength
        Should consider adding a velocity array to this Class, 
        i.e. self.velo

        Parameters
        ----------
        wv_obs : float
          Wavelength to set the zero of the velocity array.
          Often (1+z)*wrest

        Returns:
        ---------
        velo: Quantity array (km/s)
        '''
        return  (self.dispersion-wv_obs) * const.c.to('km/s')/wv_obs

    #  Box car smooth
    def box_smooth(self, nbox, preserve=False):
        """ Box car smooth spectrum and return a new one
        Is a simple wrapper to the rebin routine

        Parameters
        ----------
        nbox: integer
          Number of pixels to smooth over
        preserve: bool (False) 
          Keep the new spectrum at the same number of pixels as original

        Returns:
        --------
          XSpectrum1D of the smoothed spectrum
        """
        from xastropy.xutils import arrays as xxa
        if preserve:
            from astropy.convolution import convolve, Box1DKernel
            new_fx = convolve(self.flux, Box1DKernel(nbox))
            new_sig = convolve(self.sig, Box1DKernel(nbox))
            new_wv = self.dispersion
        else:
            # Truncate arrays as need be
            npix = len(self.flux)
            try:
                new_npix = npix // nbox # New division
            except ZeroDivisionError:
                raise ZeroDivisionError('Dividing by zero..')
            orig_pix = np.arange( new_npix * nbox )

            # Rebin (mean)
            new_wv = xxa.scipy_rebin( self.dispersion[orig_pix], new_npix )
            new_fx = xxa.scipy_rebin( self.flux[orig_pix], new_npix )
            new_sig = xxa.scipy_rebin( self.sig[orig_pix], new_npix ) / np.sqrt(nbox)

        # Return
        return XSpectrum1D.from_array(new_wv, new_fx,
                                      uncertainty=apy.nddata.StdDevUncertainty(new_sig))

    # Splice two spectra together
    def gauss_smooth(self, fwhm, **kwargs):
        ''' Smooth a spectrum with a Gaussian
        Need to consider smoothing the uncertainty array

        Parameters
        ----------
        fwhm: float
            FWHM of the Gaussian in pixels (unitless)

        Returns:
        --------
          XSpectrum1D of the smoothed spectrum
        Returns:
        '''
        # Import
        from linetools.spectra import convolve as lsc

        # Apply to flux
        new_fx = lsc.convolve_psf(self.flux.value, fwhm, **kwargs)*self.flux.unit

        # Return
        return XSpectrum1D.from_array(self.dispersion, new_fx,
                                      uncertainty=self.uncertainty)

    # Splice two spectra together
    def splice(self, spec2, wvmx=None):
        ''' Combine two spectra
        It is assumed that the internal spectrum is *bluer* than
        the input spectrum.

        Parameters
        ----------
        spec2: Spectrum1D
          Second spectrum
        wvmx: Quantity
          Wavelength to begin splicing *after*

        Returns:
        ----------
        spec3: Spectrum1D
          Spliced spectrum
        '''
        # Begin splicing after the end of the internal spectrum
        if wvmx is None:
            wvmx = np.max(self.dispersion)
        # 
        gdp = np.where(spec2.dispersion > wvmx)[0]
        # Concatenate
        new_wv = np.concatenate( (self.dispersion.value, 
            spec2.dispersion.value[gdp]) )
        uwave = u.Quantity(new_wv, unit=self.wcs.unit)
        new_fx = np.concatenate( (self.flux.value, 
            spec2.flux.value[gdp]) )
        if self.sig is not None:
            new_sig = np.concatenate( (self.sig, spec2.sig[gdp]) )
        # Generate
        spec3 = XSpectrum1D.from_array(uwave, u.Quantity(new_fx),
                                         uncertainty=StdDevUncertainty(new_sig))
        # Return
        return spec3

    # Write to fits
    def write_to_fits(self, outfil, clobber=True, add_wave=False):
        ''' Write to a FITS file
        Should generate a separate code to make a Binary FITS table format

        Parameters
        ----------
        outfil: String
          Name of the FITS file
        clobber: bool (True)
          Clobber existing file?
        add_wave: bool (False)
          Force writing of wavelength array
        '''
        # TODO
        #  1. Add unit support for wavelength arrays

        from specutils.io import write_fits as sui_wf
        prihdu = sui_wf._make_hdu(self.data)  # Not for binary table format
        prihdu.name = 'FLUX'
        multi = 0 #  Multi-extension?

        # Type
        if type(self.wcs) is Spectrum1DPolynomialWCS:  # CRVAL1, etc. WCS
            # WCS
            wcs = self.wcs
            wcs.write_fits_header(prihdu.header)
            # Error array?
            if self.sig is not None:
                sighdu = fits.ImageHDU(self.sig)
                sighdu.name='ERROR'
                # 
                if add_wave:
                    wvhdu = fits.ImageHDU(self.dispersion.value)
                    wvhdu.name = 'WAVELENGTH'
                    hdu = fits.HDUList([prihdu, sighdu, wvhdu])
                else:
                    hdu = fits.HDUList([prihdu, sighdu])
                multi=1
            else:
                hdu = prihdu

        elif type(self.wcs) is Spectrum1DLookupWCS: # Wavelengths as an array (without units for now)
            # Add sig, wavelength to HDU
            sighdu = fits.ImageHDU(self.sig)
            sighdu.name='ERROR'
            wvhdu = fits.ImageHDU(self.dispersion.value)
            wvhdu.name = 'WAVELENGTH'
            hdu = fits.HDUList([prihdu, sighdu, wvhdu])
            multi=1
        else:
            raise ValueError('write_to_fits: Not ready for this type of spectrum wavelengths')

        # Deal with header
        if hasattr(self,'head'):
            hdukeys = prihdu.header.keys()
            # Append ones to avoid
            hdukeys = hdukeys + ['BUNIT','COMMENT','', 'NAXIS2', 'HISTORY']
            for key in self.head.keys():
                # Use new ones
                if key in hdukeys:
                    continue
                # Update unused ones
                try:
                    prihdu.header[key] = self.head[key]
                except ValueError:
                    raise ValueError('l.spectra.utils: Bad header key card')
            # History
            if 'HISTORY' in self.head.keys():
                # Strip \n
                tmp = str(self.head['HISTORY']).replace('\n',' ')
                try:
                    prihdu.header.add_history(str(tmp))
                except ValueError:
                    import pdb
                    pdb.set_trace()

        # Write
        hdu.writeto(outfil, clobber=clobber)
        print('Wrote spectrum to {:s}'.format(outfil))

