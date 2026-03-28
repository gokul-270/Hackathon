#!/usr/bin/env bash
#Launch pigpiod library in the start for the vehicle --> by gokul
echo "Loading pigpiod library"
echo "grobomac" | sudo -S pigpiod
sleep 2

pigs modes 14 w
pigs w 14 1
 
