"""A class that reads all output data files generated by Lagranto in
   a specified directory.

********************************************************************************

   Copyright 2008-2014 Deutsches Zentrum fuer Luft- und Raumfahrt e.V.

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.

********************************************************************************

Usage:
======

    lout = LagrantoOutputReader(<complete path to output files>)

That's it! After this call the data of trajectories read from lsl* files
can be accessed via

    lout.data[trajectoryIndex][<variable_name>],

the data of lsl* files (statistics of trajectories in ls* files) via

    lout.stats[<output_filename>][<variable_name>],

where <trajectoryIndex> is the number of the trajectory (increasing with each
file) (if more than one trajectories were computed from a start region or in
scf mode; if there is only one file with one trajectory, this number takes
the value 0).

Trajectory data is stored in NumPy arrays.

Call

    len(lout.data)

to see how many trajectories have been read, and
which files have been read, and

    lout.data[trajectoryIndex].keys()

to see which variables are available for a trajectory. Call

    lout.meta[trajectoryIndex]

to view the metadata available for a given trajectory.


Example:
========

    import lagrantooutputreader
    lout = lagrantooutputreader.LagrantoOutputReader( \
                'output/ntr_20070401_00_f24_1_j_o30/')
    len(lout.data)
    lout.data[10].keys()
    lout.data[10]['PV']
    lout.meta[10]
    .. etc ..

AUTHORS:
========

* Marc Rautenhaus (mr)

"""

# standard library imports
import datetime
import sys

import copy
import logging
import os
import pickle

# related third party imports
import numpy

# local application imports


#
# CLASS LagrantoOutputReader
#


class LagrantoOutputReader(object):
    """A class that reads all output data files generated by Lagranto in
       a specified directory.
    """

    def __init__(self, lagrantoOutputPath, of=sys.stdout):
        """Initialise the reader and read all ls* and lsl* files contained
           in the path argument.

        Arguments:
        lagrantoOutputPath -- path to the directory containing the Lagranto
                              output files. All lsl* and ls* files in this
                              directory will be read.

        Keyword arguments:
        of -- output for all print statements, has to be an object
              with a *write()* method, e.g. a file; if not
              specified sys.stdout is taken
        """

        #
        # Expand path to user home if necessary and test if the argument is
        # a valid path. Raise an exception if not.
        self.lagrantoOutputPath = os.path.expanduser(lagrantoOutputPath)
        if not os.path.isdir(self.lagrantoOutputPath):
            raise ValueError("Argument " +
                             self.lagrantoOutputPath +
                             " does not represent a valid path.")

        self.of = of
        self.data = []  # stores trajectory data from lsl* files
        self.meta = []  # stores metadata belonging to the trajectories
        self.stats = {}  # stores data from ls* files

        #
        # Read all files contained in lagrantoOutputPath.
        self.__readFilesInDirectory()

    def __read_lslFile(self, fname):
        """Parse a Lagranto lsl-file and reads the data into NumPy arrays.
           Also read the corresponding metadata files, if existent.

        Data contained in the file is accessible under
            self.data[trajectoryIndex][variablename]
            self.meta[trajectoryIndex][metatagname]
        after this method has been executed.

        self.meta[trajectoryIndex] will contain at least the variables 'file'
        and 'startttime_filename', indicating the file from which the trajectory
        was read and the start time, determined from the filename or the
        directory name (datetime object). If a metadata file is present,
        the fields 'startcoordinates', 'startttime' and 'duration' will contain
        values from the start points list passed to LagrantoWrapper,
        metadata additionally specified together with the start coordinates
        will also be added to self.meta[trajectoryIndex].

        Arguments:
        fname -- file name of the lsl-file, without path (i.e. only 'lsl_...').
        """

        logging.debug(u"Parsing output file '{}'".format(fname))

        #
        # Open the lsl text file and read its contents into the list 'lines',
        # containing the individual text lines as elements.
        flsl = open(os.path.join(self.lagrantoOutputPath, fname), 'r')
        lines = flsl.readlines()

        #
        # Open and read the metadata file, if existent.
        metafile = os.path.join(self.lagrantoOutputPath, fname) + '.meta.pyl'
        if os.path.exists(metafile):
            logging.debug(u"Reading metadata file '{}'".format(os.path.basename(metafile)))
            filehandler = open(metafile, 'r')
            startCoordinates = pickle.load(filehandler)
            startTime = pickle.load(filehandler)
            duration = pickle.load(filehandler)
            filehandler.close()
        else:
            logging.debug(u"No metadata file '{}' found.".format(metafile))
            startCoordinates = None
            startTime = None
            duration = None

        #
        # Data contained in the current file will be appended to self.data,
        # hence be accessible under self.data[startIndex + X], where
        # startIndex is the length of self.data at the time this method is
        # called.
        startIndex = len(self.data)
        #
        # Get the current filename (without path) and determine the trajectory
        # start time from this name. These two variable will be stored in
        # self.meta[trajectoryIndex]['file'] and ['starttime_filename'],
        # respectively. Even if no metadata file was found, these two
        # variables will be available for each trajectory.
        filename = os.path.basename(fname)
        startTimeFile = self.__getDateTimeFromName(filename)
        if not startTimeFile:
            startTimeFile = self.initTimeDir

        #
        # Start to parse the file: Get the index of the first blank line in
        # order to skip the header.
        firstBlank = lines.index(" \n")
        #
        # Variable names are contained in the line following the first
        # blank line. Initialise empty lists for each variable.
        varNames = lines[firstBlank + 1].split()
        emptyVariableDictionaryTemplate = {}
        for varName in varNames:
            emptyVariableDictionaryTemplate[varName] = []
        self.data.append(copy.deepcopy(emptyVariableDictionaryTemplate))

        #
        # Iterate through the lines containing the data (lines 4ff. after
        # the first blank line. Append the numerical values, converted to
        # floats, to the data lists identified by the variable names (the
        # [-1] index references the last element). If a blank line is
        # encountered, this indicates a new trajectory in the file. Hence,
        # append a new trajectory to self.data.
        for dataLine in lines[firstBlank + 4:]:
            if dataLine == " \n":
                self.data.append(
                    copy.deepcopy(emptyVariableDictionaryTemplate))
            for varName, strValue in zip(varNames, dataLine.split()):
                self.data[-1][varName].append(float(strValue))

        #
        # Finally, for each trajectory from this file: convert the lists
        # with the numerical data to NumPy arrays for faster access; create
        # a metadata dictionary (containing at least the filename and start
        # time determined from this name or the directory name) and append
        # it to self.meta.
        for i in range(startIndex, len(self.data)):
            for varName in varNames:
                self.data[i][varName] = numpy.array(self.data[i][varName])
            metadict = {'file': filename,
                        'starttime_filename': startTimeFile}
            # If metadata is present, check if a metadata dictionary was
            # specified for this trajectory (last element of the start
            # coordinates list is a dictionary, cf. lagranto.py). If yes,
            # add the contained elements to self.meta. Store start coordinates,
            # time and duration in the metadata dictionary.
            if startCoordinates is not None:
                if isinstance(startCoordinates[i - startIndex][-1], dict):
                    metadict.update(startCoordinates[i - startIndex].pop())
                metadict['startcoordinates'] = startCoordinates[i - startIndex]
                metadict['starttime'] = startTime
                metadict['duration'] = duration
            self.meta.append(metadict)

    def __read_lsFile(self, fname):
        """Parse a Lagranto ls-file and reads the data into NumPy arrays.

        Data contained in the file is accessible under
            self.stats[filename][variablename]
        after this method has been executed.

        Arguments:
        fname -- file name of the lsl-file, without path (i.e. only 'ls_...').
        """
        #
        # This method is similar to __read_lslFile(). Only those parts of the
        # source code are documented that differ from __read_lslFile().
        logging.debug("Parsing output file %s" % fname)

        flsl = open(os.path.join(self.lagrantoOutputPath, fname), 'r')
        lines = flsl.readlines()

        dataKey = os.path.basename(fname)
        self.stats[dataKey] = {}
        self.starttimes[dataKey] = self.__getDateTimeFromName(dataKey)
        if not self.starttimes[dataKey]:
            self.starttimes[dataKey] = self.initTimeDir

        firstBlank = lines.index(" \n")

        varNames = lines[firstBlank + 1].split()

        #
        # In the ls-files, all variables except for time, lat and lon are
        # stored with an additional column representing the standard deviation
        # of the trajectories for Lagranto runs in which more than one
        # trajectories have been computed. These columns aren't named
        # in the text files, hence we have to add their names to the
        # varNames list here. The convention used is the original variable
        # name appended by a '_stddev'. Note that the first three variabe
        # names (i.e. time, lat, lon) are skipped in this loop.
        for varName in varNames[3:]:
            varNames.insert(varNames.index(varName) + 1, varName + "_stddev")

        #
        # Also, an additional column following the variable data is stored in
        # the text file, containing the number of trajectories that have
        # left the model domain after time t. We append a new variable to our
        # list that will accomodate this information.
        varNames.append("evolution_of_ntraout")

        for varName in varNames:
            self.stats[dataKey][varName] = []

        #
        # Get the index of the second blank line to get the end of the data
        # section.
        secondBlank = lines.index(" \n", firstBlank + 1)

        #
        # Process the data section.
        for dataLine in lines[firstBlank + 3:secondBlank]:
            for varName, strValue in zip(varNames[:-1], dataLine.split()):
                self.stats[dataKey][varName].append(float(strValue))

        #
        # Process the second data section containing 'evolution_of_ntraout'.
        for dataLine in lines[secondBlank + 4:]:
            strValue = dataLine.split()[1]
            self.stats[dataKey]["evolution_of_ntraout"].append(float(strValue))

        for varName in varNames:
            self.stats[dataKey][varName] = numpy.array(self.stats[dataKey][varName])

    def __readFilesInDirectory(self):
        """Read all files contained in the directory passed to the constructor.

        Arguments:
        -- None --
        """
        #
        # Remove trailing '/' if present, so that os.path.split() returns the
        # last subdirectory (var[-1] is short for var[len(var)-1]).
        subdirname = self.lagrantoOutputPath
        if subdirname[-1] == '/':
            subdirname = subdirname[:-1]
        subdirname = os.path.split(subdirname)[1]

        #
        # Try to extract the init time from the directory name.
        self.initTimeDir = self.__getDateTimeFromName(subdirname)

        #
        # Get a list of files in the directory given by lagrantoOutputPath.
        fileList = os.listdir(self.lagrantoOutputPath)

        #
        # Extract all lsl* data files from the list and call the corresponding
        # read method.
        lslFiles = [fname for fname in fileList
                    if fname.startswith("lsl_") and
                    not fname.endswith(".meta.pyl")]
        for fname in lslFiles:
            self.__read_lslFile(fname)

        #
        # The same for all ls* data files.
        lsFiles = [fname for fname in fileList
                   if fname.startswith("ls_") and
                   not fname.endswith(".meta.pyl")]
        for fname in lsFiles:
            self.__read_lsFile(fname)

    def __getDateTimeFromName(self, name):
        """Look for a sequence of format YYYYMMDD_hh[mm] in name (where mm is)
           optional and return a datetime object.
        """
        #
        # Try to extract a time of format YYYYMMDD_hh[mm] from 'name'.
        # Start at each index from the beginning of the string 'name'
        # to len(name)-11[13] (the time is 11[13] characters long) and try
        # to convert the part of the string to a datetime object. If successful,
        # break out of the loop. If the format YYYYMMDD_hhmm is successful,
        # return this value, otherwise try YYYYMMDD_hh.
        timeFormat = ["%Y%m%d_%H%M", "%Y%m%d_%H"]  # YYYYMMDD_hh[mm]
        timeFormatLen = [13, 11]

        for tf, tflen in zip(timeFormat, timeFormatLen):
            for i in range(len(name) - tflen):
                try:
                    time = datetime.datetime.strptime(name[i:i + tflen], tf)
                except ValueError:
                    pass
                else:
                    return time
        return None



#
# Perform some tests if the module is called directly. Remember to adjust the
# paths before executing this script.
if __name__ == "__main__":
    lout = LagrantoOutputReader(
        '/path/to/lagranto/output/scf_ensemble_test_N01')
