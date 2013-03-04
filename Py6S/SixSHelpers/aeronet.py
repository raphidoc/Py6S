# This file is part of Py6S.
#
# Copyright 2012 Robin Wilson and contributors listed in the CONTRIBUTORS file.
#
# Py6S is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Py6S is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with Py6S.  If not, see <http://www.gnu.org/licenses/>.

import numpy as np
from scipy.interpolate import interp1d
import dateutil.parser
import tempfile
import warnings
from Py6S import *


class Aeronet:
  """Contains functions for importing data from AERONET measurements."""
  
  @classmethod
  def import_aeronet_data(cls, s, filename, time):
    """Imports data from an AERONET data file to a given SixS object.
    
    This requires a valid AERONET data file. The type of file required is a *Combined file* for All Points (Level
    1.5 or 2.0)
    
    To download a file like this:
    
    1. Go to http://aeronet.gsfc.nasa.gov/cgi-bin/webtool_opera_v2_inv
    
    2. Choose the site you want to get data from
    
    3. Tick the box near the bottom labelled as "Combined file (all products without phase functions)"
    
    4. Choose either Level 1.5 or Level 2.0 data. Level 1.5 data is unscreened, so contains far more data meaning it is more likely for you to find data near your specified time.
    
    5. Choose All Points under Data Format
    
    6. Download the file
    
    7. Unzip
    
    8. Pass the filename to this function
    
    
    Arguments:
    
    * ``s`` -- A :class:`.SixS` instance whose parameters you would like to set with AERONET data
    * ``filename`` -- The filename of the AERONET file described above
    * ``time`` -- The date and time of the simulation you want to run, used to choose the AERONET data which is closest
      in time. Provide this as a string in almost any format, and Python will interpret it. For example, ``"12/03/2010 15:39"``. When dates are ambiguous, the parsing routine will favour DD/MM/YY rather than MM/DD/YY.
    
    Return value:
    
    The function will return ``s`` with the ``aero_profile`` and ``aot550`` fields filled in from the AERONET data.
    
    Notes:
    
    Beware, this function makes a number of assumptions and performs a number of possibly-inaccurate steps.
    
    1. The refractive indices for aerosols are only provided in AERONET data at a few wavelengths, but 6S requires
    them at 20 wavelengths. Thus, the refractive indices are extrapolated outside of their original range, to provide
    the necessary data. This is generally not a good idea, but is acceptable here as the refractive indices seem to
    change very little any way, and it is the only possible way to do it!
    
    2. The AERONET measurement of AOT at 500nm is used for the 6S input of AOT at 550nm.
    
    """
    filename = cls._raw(filename)
    tmp_file, tmp_file_name = tempfile.mkstemp(prefix="tmp_aeronet_", text=True)
    
    # Get the given time from the user
    given_time = dateutil.parser.parse(time, dayfirst=True)
    
    # Join first two columns of file
    in_file = open(filename, "r")
    out_file = open(tmp_file_name, "w")
    for line in in_file:
      line = line.replace(",", " ", 1)
      out_file.write(line)
    out_file.close()
    
    # Get the header line
    f = open(tmp_file_name, "r")
    lines = f.readlines()
    header = lines[3]
    spl_header = header.split(",")
    
    refr = []
    refi = []
    wavelengths = []
    radii = []
    radii_indices = []

    aot_indices = []
    aot_wavelengths = []
    
    # Extract the indices of the columns we want, plus the radii and the wavelengths
    for i in range(len(spl_header)):
      h = spl_header[i]
      if "REFR" in h:
        refr.append(i)
      elif "REFI" in h:
        refi.append(i)
        wv = h.replace("(", "")
        wv = wv.replace(")", "")
        wv = wv.replace("REFI", "")
        wavelengths.append(float(wv)/1000)
      elif "AOT_" in h:
        wv = h.replace("AOT_", "")
        wv = float(wv)
        aot_wavelengths.append(wv)
        aot_indices.append(i)
      else:
        try:
          rad = float(h)
        except:
          continue
        radii.append(rad)
        radii_indices.append(i)
    
    date_conv = lambda x: dateutil.parser.parse(x.replace(":", "/", 2), dayfirst=True)
    
    ### Load the radii data from the CSV file
    a = np.genfromtxt(tmp_file_name, delimiter=',', skip_header=4,
          usecols=[0] + radii_indices, converters={0: date_conv})
    
    
    # Select the row with the closest time to the given
    diff = a['f0'] - given_time
    diff = abs(diff)
    index = np.argmax(diff == min(diff))
    row = a[index]
    
    
    dvdlogr = list(row)[1:]
    
    sixs_wavelengths = [0.350, 0.400, 0.412, 0.443, 0.470, 0.488, 0.515, 0.550, 0.590, 0.633, 0.670, 0.694, 0.760,
          0.860, 1.240, 1.536, 1.650, 1.950, 2.250, 3.750]
    
    ### Load the refractive indices data from the CSV file
    a = np.genfromtxt(tmp_file_name, delimiter=',', skip_header=4,
          usecols=[0] + refr + refi, converters={0: date_conv})
    
    
    # Select the row with the closest time to the given
    diff = a['f0'] - given_time
    diff = abs(diff)
   

    indices_to_try = diff.argsort()
    index = 0
    row = a[indices_to_try[index]]
    
    ref_ind = list(row)[1:]

    while_has_run = False

    while np.any(np.isnan(ref_ind)):
      # Some of the refractive indices we selected are NaN
      # So raise a warning and choose the next appropriate row
      while_has_run = True
      index += 1
      row = a[indices_to_try[index]]
    
      ref_ind = list(row)[1:]

    if while_has_run:
      warnings.warn("Refractive indices were NaN at closest time, so used nearest time with data. Time difference: %s" % str(diff[index]))

    refr_values = ref_ind[:len(ref_ind)/2]
    refi_values = ref_ind[len(ref_ind)/2:]
    
    finterp_real = interp1d(wavelengths, refr_values, bounds_error=False)
    final_refr = finterp_real(sixs_wavelengths)
    final_refr = cls._remove_nans(final_refr)
    
    finterp_imag = interp1d(wavelengths, refi_values, bounds_error=False)
    final_refi = finterp_imag(sixs_wavelengths)
    final_refi = cls._remove_nans(final_refi)

    ### Load the AOT data from the CSV file
    a = np.genfromtxt(tmp_file_name, delimiter=',', skip_header=4,
          usecols=[0] + aot_indices, converters={0: date_conv})
    
    # Select the row with the closest time to the given
    diff = a['f0'] - given_time
    diff = abs(diff)
    index = np.argmax(diff == min(diff))
    row = a[index]

    # Get the AOTs from the row and select the finite (non-NaN) ones
    aots = np.array(list(row)[1:])
    mask = np.isfinite(aots)

    # Apply the mask
    wvsarr = np.array(aot_wavelengths)
    wvsarr = wvsarr[mask]
    aots = aots[mask]

    # Distance from 550nm - which is the wavelength at which AOT is wanted
    diffs = np.abs(wvsarr - 550)
    together = np.vstack((diffs, aots)).T

    together.sort(axis=0)

    wv_diff =  together[0,0]
    aot = together[0,1]

    if wv_diff > 70:
      warnings.warn("AOT measurement was taken > 70nm away from 550nm - so AOT input may not be valid. Measurement was at %d" ) 

    # Set the values in the 6S object
    s.aot550 = aot
    s.aero_profile = AeroProfile.SunPhotometerDistribution(radii, dvdlogr, final_refr, final_refi)
    
    return s
  
  @classmethod
  def _remove_nans(cls, a):
    """Removes leading or trailing NaNs from a ndarray, by repeating the closest value."""
    ind = np.where(~np.isnan(a))[0]
    first, last = ind[0], ind[-1]
    a[:first] = a[first]
    a[last + 1:] = a[last]
    
    return(a)
    
          
  @classmethod
  def _raw(cls, text):
      """Returns a raw string representation of text"""
      
      escape_dict={'\a':r'\a',
           '\b':r'\b',
           '\c':r'\c',
           '\f':r'\f',
           '\n':r'\n',
           '\r':r'\r',
           '\t':r'\t',
           '\v':r'\v',
           '\'':r'\'',
           '\"':r'\"',
           '\0':r'\0',
           '\1':r'\1',
           '\2':r'\2',
           '\3':r'\3',
           '\4':r'\4',
           '\5':r'\5',
           '\6':r'\6',
           '\7':r'\7',
           '\8':r'\8',
           '\9':r'\9'}
          
      new_string=''
      for char in text:
          try: new_string+=escape_dict[char]
          except KeyError: new_string+=char
      return new_string
