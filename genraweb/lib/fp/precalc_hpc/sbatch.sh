#!/bin/bash

##SBATCH --get-user-env
##SBATCH --mail-type BEGIN
##SBATCH --mail-type END
##SBATCH --mail-type FAIL
##SBATCH --mail-user yourlD@nmsu.edu
##SBATCH --mem-per-cpu 200M

#SBATCH --account=qsardss
#SBATCH --cpus-per-task 32
#SBATCH --job-name genra

##SBATCH --output genra.o%j

#SBATCH --ntasks 1

# These two are mutually exclusive
#SBATCH --partition debug
##SBATCH --time 1-00:00:00
