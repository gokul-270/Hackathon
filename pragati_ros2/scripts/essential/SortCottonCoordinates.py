#!/usr/bin/env python3
# This script reads the cotton_details.txt file and writes it to the output file without sorting
# It also appends the same content to a log file in /home/ubuntu/pragati/outputs/ with a timestamp
# Input file format: xpixel ypixel X Y Z (xpixel and ypixel are integers, X Y Z are floating-point numbers)
# Usage: SortCottonCordinates.py -i <InputFilePath> -o <OutputFilePath> -l <LogFilePath> -d -h/--help

from __future__ import print_function
import os
import sys
import getopt
from datetime import datetime

DEBUG = "true"
# Default file paths (aligned with aruco_detector.py)
InputFile = "/home/ubuntu/pragati/outputs/cotton_details.txt"
OutputFile = "/home/ubuntu/pragati/outputs/output.txt"
LogFile = "/home/ubuntu/pragati/outputs/aruco_points.log"  # Log file in pragati/outputs

#### Argument parsing
if DEBUG == "true":
    print("CommandLine Input: %s" % (sys.argv))

argumentList = sys.argv[1:]
options = "i:o:l:hd"
long_options = ["Input_file", "Output", "Log", "Help"]

try:
    arguments, values = getopt.getopt(argumentList, options, long_options)
    for currentArgument, currentValue in arguments:
        if currentArgument in ("-d"):
            DEBUG = "true"
            print("INFO :: DEBUG OPTION ENABLED")
        elif currentArgument in ("-h", "--Help"):
            print("Usage: %s -i <InputFilePath> -o <OutputFilePath> -l <LogFilePath> -d -h/--help" % (sys.argv[0]))
            sys.exit()
        elif currentArgument in ("-i", "--Input_file"):
            if DEBUG == "true":
                print("INFO :: -i InputfileName: %s" % (currentValue))
            InputFile = currentValue
        elif currentArgument in ("-o", "--Output"):
            if DEBUG == "true":
                print("INFO :: -o OutputFilePath: %s" % (currentValue))
            OutputFile = currentValue
        elif currentArgument in ("-l", "--Log"):
            if DEBUG == "true":
                print("INFO :: -l LogFilePath: %s" % (currentValue))
            LogFile = currentValue
except getopt.error as err:
    print(str(err))
    with open(LogFile, 'a') as log_file:
        log_file.write(f"ERROR: Command-line argument error: {str(err)}\n")
    sys.exit(1)

if DEBUG == "true":
    print("INFO :: InputFile to Read: %s" % (InputFile))
    print("INFO :: OutputFile to Write: %s" % (OutputFile))
    print("INFO :: LogFile to Append: %s" % (LogFile))

### Open Input File
try:
    with open(InputFile, 'r') as InputFileHandle:
        UnSortedList = InputFileHandle.read().splitlines()
        if DEBUG == "true":
            print("INFO :: Opened Input file (%s)" % (InputFile))
    if not UnSortedList:
        if DEBUG == "true":
            print("INFO :: No data in Inputfile (%s)" % (InputFile))
        with open(LogFile, 'a') as log_file:
            log_file.write(f"WARNING: No data in Inputfile: {InputFile}\n")
        sys.exit(1)
except IOError as e:
    print("ERROR: I/O error({0}): {1}".format(e.errno, e.strerror))
    print("ERROR: Error Opening InputFile (%s)" % (InputFile))
    with open(LogFile, 'a') as log_file:
        log_file.write(f"ERROR: I/O error opening InputFile ({InputFile}): {e.strerror}\n")
    sys.exit(1)
except Exception as e:
    print("ERROR: Exception During Opening InputFile Unexpected error: %s" % (sys.exc_info()[0]))
    with open(LogFile, 'a') as log_file:
        log_file.write(f"ERROR: Exception opening InputFile ({InputFile}): {e}\n")
    sys.exit(1)

### Open OutputFile
try:
    OutputFileHandle = open(OutputFile, 'w')
    if DEBUG == "true":
        print("INFO :: Opened Output file (%s)" % (OutputFile))
except IOError as e:
    print("ERROR: I/O error({0}): {1}".format(e.errno, e.strerror))
    print("ERROR: Error Opening OutputFile (%s)" % (OutputFile))
    with open(LogFile, 'a') as log_file:
        log_file.write(f"ERROR: I/O error opening OutputFile ({OutputFile}): {e.strerror}\n")
    sys.exit(1)
except Exception as e:
    print("ERROR: Exception During Opening OutputFile Unexpected error: %s" % (sys.exc_info()[0]))
    with open(LogFile, 'a') as log_file:
        log_file.write(f"ERROR: Exception opening OutputFile ({OutputFile}): {e}\n")
    sys.exit(1)

### Read all lines in a list
UnSortedLineOfCoordinates = []
if DEBUG == "true":
    print("#INFO :: ####Printing UnSorted List")

for i in range(len(UnSortedList)):
    try:
        coordinates = list(map(float, UnSortedList[i].split()))
        if len(coordinates) == 5:  # Validate format: xpixel ypixel X Y Z
            UnSortedLineOfCoordinates.append(coordinates)
            if DEBUG == "true":
                print(coordinates)
        else:
            if DEBUG == "true":
                print("WARNING: Invalid line format in InputFile at line %d: %s" % (i + 1, UnSortedList[i]))
            with open(LogFile, 'a') as log_file:
                log_file.write(f"WARNING: Invalid line format in InputFile at line {i + 1}: {UnSortedList[i]}\n")
    except ValueError as e:
        if DEBUG == "true":
            print("ERROR: Error parsing line %d: %s" % (i + 1, e))
        with open(LogFile, 'a') as log_file:
            log_file.write(f"ERROR: Error parsing line {i + 1}: {e}\n")
        continue

### Write values to the Output File and Log File
timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
with open(LogFile, 'a') as log_file:
    # Write timestamp to log file
    log_file.write(f"{timestamp}\n")
    for tempLine in UnSortedLineOfCoordinates:
        line = f"{int(tempLine[0])} {int(tempLine[1])} {tempLine[2]:.4f} {tempLine[3]:.4f} {tempLine[4]:.4f}"
        # Write to output.txt
        print(line, file=OutputFileHandle)
        # Append to aruco_points.log
        log_file.write(line + "\n")
    # Add a blank line between runs
    log_file.write("\n")

### Close OutputFile
OutputFileHandle.close()
if DEBUG == "true":
    print("INFO :: Processing complete. ArUco points appended to %s" % (LogFile))
