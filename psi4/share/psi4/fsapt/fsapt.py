#!/usr/bin/env python

#
# @BEGIN LICENSE
#
# Psi4: an open-source quantum chemistry software package
#
# Copyright (c) 2007-2019 The Psi4 Developers.
#
# The copyrights for code used from other parties are included in
# the corresponding files.
#
# This file is part of Psi4.
#
# Psi4 is free software; you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, version 3.
#
# Psi4 is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License along
# with Psi4; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# @END LICENSE
#

import psi4
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
import sys, os, re, math, copy

# => Global Data <= #

# H to kcal constant
H_to_kcal_ = psi4.constants.hartree2kcalmol

# SAPT Keys
saptkeys_ = [
    'Elst',
    'Exch',
    'IndAB',
    'IndBA',
    'Disp',
    'D3MZero',
    'D3MBJ',
    'Total',
]

d3keys_ = ['D3MZero', 'D3MBJ']

# Map from atom name to charge, vDW radius, nfrozen
atom_data_ = {
'H'  :  [1.0,  0.402, 0],
'HE' :  [2.0,  0.700, 0],
'LI' :  [3.0,  1.230, 1],
'BE' :  [4.0,  0.900, 1],
'B'  :  [5.0,  1.000, 1],
'C'  :  [6.0,  0.762, 1],
'N'  :  [7.0,  0.676, 1],
'O'  :  [8.0,  0.640, 1],
'F'  :  [9.0,  0.630, 1],
'NE' :  [10.0, 0.700, 1],
'NA' :  [11.0, 1.540, 5],
'MG' :  [12.0, 1.360, 5],
'AL' :  [13.0, 1.180, 5],
'SI' :  [14.0, 1.300, 5],
'P'  :  [15.0, 1.094, 5],
'S'  :  [16.0, 1.253, 5],
'CL' :  [17.0, 1.033, 5],
'AR' :  [18.0, 1.740, 5],
}

# => Standard Order-2 Analysis <= #

def readXYZ(filename):

    fh = open(filename,'r')
    lines = fh.readlines()
    lines = lines[2:]
    fh.close()

    re_xyz = re.compile(r'^\s*(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s*$')

    val = []
    for line in lines:
        mobj = re.match(re_xyz, line)
        val.append([mobj.group(1), float(mobj.group(2)), float(mobj.group(3)), float(mobj.group(4))])

    return val

def writeXYZ(filename, geom):

    fh = open(filename, 'w')
    fh.write('%d\n\n' % len(geom))
    for line in geom:
        fh.write('%6s %14.10f %14.10f %14.10f\n' % (line[0], line[1], line[2], line[3]))
    fh.close();

def readList(filename, factor = 1.0):

    fh = open(filename, 'r')
    lines = fh.readlines()
    fh.close()

    val = [float(x) * factor for x in lines]

    return val

def readBlock(filename, factor = 1.0):

    fh = open(filename, 'r')
    lines = fh.readlines()
    fh.close()

    val = []
    for line in lines:
        val.append([factor * float(x) for x in re.split(r'\s+',line.strip())])

    return val

def readFrags(filename):

    frags = {}
    fragkeys = []

    fh = open(filename, 'r')
    lines = fh.readlines()
    fh.close()

    for line in lines:
        tokens = re.split(r'\s+', line.strip())
        key = tokens[0]
        val = [int(token)-1 for token in tokens[1:]]
        frags[key] = val
        fragkeys.append(key)

    return [frags, fragkeys]

def get_natoms(frags: Dict[str, Dict[str, List[int]]]) -> Dict[str, int]:
    """Given dictionary with fragment information, returns dict with number of atoms in monomers

    Arguments
    ---------
    frags : Dict[str, Dict[str, List[int]]]
        Output dictionary from `readFrags` or `readD3Frags`

    Returns
    -------
    natoms : Dict[str, int]
        Number of atoms in each monomer
    """
    natoms = {}
    for mono, fragdict in frags.items():
        # Get number of atoms in each monomer
        na = 0
        for fname, fatoms in fragdict.items():
            if 'Link' in fname:
                continue
            na += len(fatoms)
        natoms[mono] = na

    return natoms

def readD3Frags(dirname: Optional[str] = '.') -> Dict[str, Dict[str, List[int]]]:
    """Creates a dictionary of fragments from fsapt fragment files for post-analysis

    Arguments
    ---------
    dirname : Optional[str]
        Path to directory containing F-SAPT fragment files
        Default: '.'

    Returns
    -------
    frags : Dict[str, Dict[str, List[int]]]
        Dictionary of dictionaries with fragment lists for each monomer
    """
    frags = {'A': {}, 'B': {}}
    natoms = {}
    for mono in ['A', 'B']:
        fragdict = {}
        # Read lines from frag file
        with open(f"{dirname}{os.sep}f{mono}.dat", 'r') as f:
            fraglines = f.readlines()

        # Iterate over lines, save into dict as <fragname>: [list of atom numbers]
        for l in fraglines:
            stuff = l.split()
            # Get number of atoms in each fragment
            fragdict[stuff[0]] = [int(i) for i in stuff[1:]]

        # Save fragdict into frags
        frags[mono] = fragdict

    return frags

def collapseRows(vals):
    vals2 = [0.0 for x in vals[0]]
    for row in vals:
        for k in range(len(row)):
            vals2[k] += row[k]

    return vals2

def collapseCols(val):
    vals2 = [sum(x) for x in vals]
    return vals2

def checkFragments(geom, Zs, frags):

    # Uniqueness
    taken = []
    for key, value in frags.items():
        for index in value:
            if index in taken:
                raise Exception('Atom %d is duplicated' % (index+1))
            taken.append(index)

    # Cover/Exclusion
    for ind in range(len(geom)):
        if (ind in taken) and (Zs[ind] == 0.0):
            raise Exception('Atom %d has charge 0.0, should not be in fragments.' % (ind+1))
        elif (ind not in taken) and (Zs[ind] != 0.0):
            raise Exception('Atom %d has charge >0.0, should be in fragments.' % (ind+1))

def partitionFragments(fragkeys,frags,Z,Q,completeness = 0.85):

    nA = len(Q)
    na = len(Q[0])

    nuclear_ws = {}
    orbital_ws = {}
    for key in fragkeys:
        nuclear_ws[key] = [0.0 for x in range(nA)]
        orbital_ws[key] = [0.0 for x in range(na)]

    for A in range(nA):
        for key in fragkeys:
            if A in frags[key]:
                nuclear_ws[key][A] = 1.0

    linkas = []
    for a in range(na):
        assigned = False
        for key in fragkeys:
            sum = 0.0
            for A in frags[key]:
                sum += Q[A][a]
            if sum > completeness:
                assigned = True
                orbital_ws[key][a] = 1.0
                break
        if not assigned:
            linkas.append(a)

    linkkeys = []
    links = {}
    link_nuclear_ws = {}
    link_orbital_ws = {}
    linkindex = 0;

    for a in linkas:
        sums = []
        for key in fragkeys:
            sum = 0.0
            for A in frags[key]:
                sum += Q[A][a]
            sums.append(sum)

        inds = sorted(range(len(sums)),key=lambda x:-sums[x])
        sum = sums[inds[0]] + sums[inds[1]]
        if sum <= completeness:
            raise Exception("Orbital %d is not complete over two fragments. " 
                            "To avoid this error, please try to avoid cutting "
                            "multiple bonds, aromatic rings, etc., in your "
                            "definitions of fragments." % (a+1))
        key1 = fragkeys[inds[0]]
        key2 = fragkeys[inds[1]]

        Ainds = sorted(range(nA),key = lambda x:-Q[x][a])
        sum = Q[Ainds[0]][a] + Q[Ainds[1]][a]
        if sum <= completeness:
            raise Exception("Orbital %d is not complete over two link atoms. "
                            "To avoid this error, please try to avoid cutting "
                            "multiple bonds, aromatic rings, etc., in your "
                            "definitions of fragments." % (a+1))
        A1 = Ainds[0]
        A2 = Ainds[1]

        nuclear_ws[key1][A1] -= 1.0 / Z[A1]
        nuclear_ws[key2][A2] -= 1.0 / Z[A2]

        linkname = 'Link-%d' % (linkindex+1);
        linkindex+=1;

        linkkeys.append(linkname)
        links[linkname] = [A1, A2]
        link_nuclear_ws[linkname] = [0.0 for x in range(nA)]
        link_orbital_ws[linkname] = [0.0 for x in range(na)]

        link_nuclear_ws[linkname][A1] += 1.0 / Z[A1]
        link_nuclear_ws[linkname][A2] += 1.0 / Z[A2]
        link_orbital_ws[linkname][a] = 1.0

    fragkeys = fragkeys + linkkeys
    for key in linkkeys:
        frags[key] = links[key]
        orbital_ws[key] = link_orbital_ws[key]
        nuclear_ws[key] = link_nuclear_ws[key]

    total_ws = {}
    for key in fragkeys:
        total_ws[key] = nuclear_ws[key] + orbital_ws[key]

    return [fragkeys, frags, nuclear_ws, orbital_ws, total_ws]

def printFrag(geom, Z, Q, fragkeys, frags, nuclear_ws, orbital_ws, filename):

    fh = open(filename, 'w')

    fh.write('   => Geometry <=\n\n')
    for k in range(len(geom)):
        fh.write('%4d %4s %11.3f %11.3f %11.3f\n' % (k+1, geom[k][0], geom[k][1], geom[k][2], geom[k][3]))
    fh.write('\n')

    fh.write('   => Fragments <=\n\n')
    for key in fragkeys:
        if len(key) > 4 and key[0:4] == 'Link':
            continue
        fh.write('%10s: ' % (key),)
        for val in frags[key]:
            fh.write('%3d ' % (val+1),)
        fh.write('\n')
    fh.write('\n')

    fh.write('   => Links <=\n\n')
    for key in fragkeys:
        if not (len(key) > 4 and key[0:4] == 'Link'):
            continue
        fh.write('%10s: ' % (key),)
        for val in frags[key]:
            fh.write('%3d ' % (val+1),)
        fh.write('\n')
    fh.write('\n')

    fh.write('   => Orbitals <=\n\n')
    for key in fragkeys:
        fh.write('%10s: ' % (key),)
        for k in range(len(orbital_ws[key])):
            if orbital_ws[key][k] != 0.0:
                fh.write('%3d ' % (k+1),)
        fh.write('\n')
    fh.write('\n')


    fh.write('   =>  Nuclear Weights <=\n\n')
    for key in fragkeys:
        fh.write('%10s: ' % (key),)
        for k in range(len(nuclear_ws[key])):
            if nuclear_ws[key][k] != 0.0:
                fh.write('%3d (%11.3f) ' % ((k+1), nuclear_ws[key][k] * Z[k]))
        fh.write('\n')
    fh.write('\n')

    fh.write('  => Charges <=\n\n')
    for key in fragkeys:
        Zval = sum([nuclear_ws[key][k] * Z[k] for k in range(len(Z))])
        Yval = 2.0 * sum(orbital_ws[key])
        fh.write('%10s: Z = %11.3f, Y = %11.3f, Q = %11.3f\n' % (key, Zval, Yval, Zval - Yval))
    fh.write('\n')

    fh.write('   => Orbital Check (Loss in Docc) <=\n\n')

    for key in fragkeys:
        fh.write('    Fragment: %s:\n' % key)
        for k in range(len(orbital_ws[key])):
            if orbital_ws[key][k] == 0.0:
                continue
            occ = 0.0
            for atom in frags[key]:
                occ += Q[atom][k]
            loss = 1.0 - occ
            fh.write('    %4d: %11.3f\n' % (k+1, loss))
    fh.write('\n')

    fh.close()

def extractOsaptData(filepath):

    vals = {}
    vals['Elst']  = np.array(readBlock('%s/Elst.dat'  % filepath, H_to_kcal_))
    vals['Exch']  = np.array(readBlock('%s/Exch.dat'  % filepath, H_to_kcal_))
    vals['IndAB'] = np.array(readBlock('%s/IndAB.dat' % filepath, H_to_kcal_))
    vals['IndBA'] = np.array(readBlock('%s/IndBA.dat' % filepath, H_to_kcal_))
    # Read exact F-SAPT0 dispersion data
    try:
        vals['Disp'] = readBlock('%s/Disp.dat'  % filepath, H_to_kcal_) # Exact F-SAPT0 Dispersion
    except FileNotFoundError:
        print('No exact dispersion present.  Copying & zeroing `Elst.dat`->`Disp.dat`, and proceeding.\n')
        vals['Disp'] = np.zeros_like(np.array(vals['Elst']))

    # Read empirical F-SAPT0-D dispersion data
    for d3disp in ['D3MZero', 'D3MBJ']:
        try:
            vals[d3disp] = np.loadtxt(f"{filepath}{os.sep}{d3disp}.dat") # Empirical F-SAPT0-D3M(0) Dispersion
        except (FileNotFoundError, OSError):
            vals[d3disp] = np.zeros_like(np.array(vals['Elst']))

    # For total, only include exact terms
    vals['Total'] = [[0.0 for x in vals['Elst'][0]] for x2 in vals['Elst']]
    for key in ['Elst', 'Exch', 'IndAB', 'IndBA', 'Disp']:
        for k in range(len(vals['Total'])):
            for l in range(len(vals['Total'][0])):
                vals['Total'][k][l] += vals[key][k][l]

    # Original fsapt code
    #vals['Disp']  = readBlock('%s/Disp.dat'  % filepath, H_to_kcal_)
    #vals['Total'] = [[0.0 for x in vals['Elst'][0]] for x2 in vals['Elst']]
    #for key in ['Elst', 'Exch', 'IndAB', 'IndBA', 'Disp']:
    #    for k in range(len(vals['Total'])):
    #        for l in range(len(vals['Total'][0])):
    #            vals['Total'][k][l] += vals[key][k][l]

    return vals

def fragmentD3Disp(d3disp: np.ndarray, frags: Dict[str, Dict[str, List[str]]]) -> Tuple[float, Dict[str, Dict[str, float]]]:
    """Fragments atomic pairwise dispersion contributions from DFTD3 for inclusion in F-SAPT-D.
    Arguments
    ---------
    d3disp : numpy.ndarray[float]
        (NA, NB) array of atom-pairwise dispersion computed by DFTD3
    frags : Dict[str, Dict[str, List[str]]]
        Dictionary containing fragment information read from `fA.dat` and `fB.dat`
    natoms : Dict[str, int]
        Dictionary containing number of atoms in each monomer
    Returns
    -------
    Edisp : float
        Dispersion energy computed from pairwise analysis
    D3pairs : Dict[str, Dict[str, float]]
        Dictionary containing reduced order-2 dispersion interactions between fragments
    """
    # Get (NA, NB) slice of d3disp
    natoms = get_natoms(frags)
    AxBd3disp = d3disp[:natoms['A'], natoms['A']:]
    #print('AxB slice shape: ',AxBd3disp.shape)
    #print(AxBd3disp)

    # Iterate over fragments, pull out relevant contributions to each
    D3frags = {}
    Edisp = 0.0
    for fA, idA in frags['A'].items():
        if 'Link' in fA:
            continue
        idA = np.array(idA)
        D3frags[fA] = {}
        for fB, idB in frags['B'].items():
            if 'Link' in fA:
                continue
            idB = np.array(idB) - natoms['A']
            # Build indexing mask for order2 fA@fB interaction
            mask = np.zeros_like(AxBd3disp, dtype='bool')
            for i in idA:
                for j in idB:
                    mask[i,j] = True
            # Add up contributions from fA@fB block
            Edisp += AxBd3disp[mask].sum() * H_to_kcal_
            D3frags[fA][fB] = AxBd3disp[mask].sum() * H_to_kcal_

    return Edisp, D3frags

def buildOrder2FsaptD(order2r: Dict[str, Dict[str, Dict[str, float]]], frags: Dict[str, Dict[str, List[str]]]) -> Dict[str, Dict[str, Dict[str, float]]]:
    """Builds total F-SAPT--D from order2r dict containing F-SAPT terms and -D dispersion.

    Arguments
    ---------
    order2r : Dict[str, Dict[str, Dict[str, float]]]
        Dictionary containing reduced order 2 F-SAPT fragment analysis
    frags : Dict[str, Dict[str, List[str]]]
        Dictionary containing fragment information read from `fA.dat` and `fB.dat`

    Returns
    -------
    D3order2r : Dict[str, Dict[str, Dict[str, float]]]
        Dictionary containing reduced order 2 F-SAPT fragment analysis, with total F-SAPT--D if -D disp present
    """
    flavors = {'F-SAPT0-D3MBJ': ['Elst', 'Exch', 'IndAB', 'IndBA', 'D3MBJ'],
               'F-SAPT0-D3MZero': ['Elst', 'Exch', 'IndAB', 'IndBA', 'D3MZero']
              }

    for flavor, terms in flavors.items():
        # Add term for total F-SAPT--D to order2r
        order2r[flavor] = {}
        # iterate over fA:fB order2 pairs
        for keyA in frags['A']:#.keys():
            order2r[flavor][keyA] = {}
            for keyB in frags['B']:#.keys():
                val = 0.0
                # Add up contributions from terms to get total F-SAPT--D energy
                for term in terms:
                    val += order2r[term][keyA][keyB]
                # Save F-SAPT--D energy in order2r[fsapt-d flavor][keyA][keyB]
                order2r[flavor][keyA][keyB] = val

    return order2r

def extractOrder2Fsapt(osapt, wsA, wsB, frags):

    vals = {}
    for key, value in osapt.items():
        # No full order 2 analysis for D3 dispersion, only reduced.  Fragment separately
        if 'D3' in key:
            Edisp, vals[key] = fragmentD3Disp(value, frags)
        else:
            vals[key] = {}
            for keyA, valueA in wsA.items():
                vals[key][keyA] = {}
                for keyB, valueB in wsB.items():
                    val = 0.0
                    for k in range(len(valueA)):
                        for l in range(len(valueB)):
                            val += valueA[k] * valueB[l] * value[k][l]
                    vals[key][keyA][keyB] = val

    return vals

def collapseLinks(order2, frags, Qs, orbital_ws, links5050):

    vals = {}
    for key in order2.keys():
        if 'D3' in key:
            vals[key] = order2[key].copy()
        else:
            vals[key] = {}
        for keyA in frags['A'].keys():
            if len(keyA) > 4 and keyA[:4] == 'Link':
                continue
            vals[key][keyA] = {}
            for keyB in frags['B'].keys():
                if len(keyB) > 4 and keyB[:4] == 'Link':
                    continue
                vals[key][keyA][keyB] = order2[key][keyA][keyB]

    for key in order2.keys():
        if 'D3' in key:
            continue
        for keyA in frags['A'].keys():
            if not (len(keyA) > 4 and keyA[:4] == 'Link'):
                continue
            for keyB in frags['B'].keys():
                if (len(keyB) > 4 and keyB[:4] == 'Link'):
                    continue

                energy = order2[key][keyA][keyB]

                atom1A = frags['A'][keyA][0]
                atom2A = frags['A'][keyA][1]

                orbA = orbital_ws['A'][keyA].index(1.0)

                if links5050:
                    Q1A = 0.5
                    Q2A = 0.5
                else:
                    Q1A = Qs['A'][atom1A][orbA]
                    Q2A = Qs['A'][atom2A][orbA]

                V1A = Q1A / (Q1A + Q2A)
                V2A = Q2A / (Q1A + Q2A)

                key1A = ''
                for keyT, value in frags['A'].items():
                    if len(keyT) > 4 and keyT[:4] == 'Link':
                        continue
                    if atom1A in value:
                        key1A = keyT
                        break

                key2A = ''
                for keyT, value in frags['A'].items():
                    if len(keyT) > 4 and keyT[:4] == 'Link':
                        continue
                    if atom2A in value:
                        key2A = keyT
                        break

                vals[key][key1A][keyB] += V1A * energy
                vals[key][key2A][keyB] += V2A * energy

    for key in order2.keys():
        if 'D3' in key:
            continue
        for keyA in frags['A'].keys():
            if (len(keyA) > 4 and keyA[:4] == 'Link'):
                continue
            for keyB in frags['B'].keys():
                if not (len(keyB) > 4 and keyB[:4] == 'Link'):
                    continue

                energy = order2[key][keyA][keyB]

                atom1B = frags['B'][keyB][0]
                atom2B = frags['B'][keyB][1]

                orbB = orbital_ws['B'][keyB].index(1.0)

                if links5050:
                    Q1B = 0.5
                    Q2B = 0.5
                else:
                    Q1B = Qs['B'][atom1B][orbB]
                    Q2B = Qs['B'][atom2B][orbB]

                V1B = Q1B / (Q1B + Q2B)
                V2B = Q2B / (Q1B + Q2B)

                key1B = ''
                for keyT, value in frags['B'].items():
                    if len(keyT) > 4 and keyT[:4] == 'Link':
                        continue
                    if atom1B in value:
                        key1B = keyT
                        break

                key2B = ''
                for keyT, value in frags['B'].items():
                    if len(keyT) > 4 and keyT[:4] == 'Link':
                        continue
                    if atom2B in value:
                        key2B = keyT
                        break

                vals[key][keyA][key1B] += V1B * energy
                vals[key][keyA][key2B] += V2B * energy

    for key in order2.keys():
        if 'D3' in key:
            continue
        for keyA in frags['A'].keys():
            if not (len(keyA) > 4 and keyA[:4] == 'Link'):
                continue
            for keyB in frags['B'].keys():
                if not (len(keyB) > 4 and keyB[:4] == 'Link'):
                    continue

                energy = order2[key][keyA][keyB]

                atom1A = frags['A'][keyA][0]
                atom2A = frags['A'][keyA][1]
                atom1B = frags['B'][keyB][0]
                atom2B = frags['B'][keyB][1]

                orbA = orbital_ws['A'][keyA].index(1.0)
                orbB = orbital_ws['B'][keyB].index(1.0)

                if links5050:
                    Q1A = 0.5
                    Q2A = 0.5
                    Q1B = 0.5
                    Q2B = 0.5
                else:
                    Q1A = Qs['A'][atom1A][orbA]
                    Q2A = Qs['A'][atom2A][orbA]
                    Q1B = Qs['B'][atom1B][orbB]
                    Q2B = Qs['B'][atom2B][orbB]

                V1A = Q1A / (Q1A + Q2A)
                V2A = Q2A / (Q1A + Q2A)
                V1B = Q1B / (Q1B + Q2B)
                V2B = Q2B / (Q1B + Q2B)

                key1A = ''
                for keyT, value in frags['A'].items():
                    if len(keyT) > 4 and keyT[:4] == 'Link':
                        continue
                    if atom1A in value:
                        key1A = keyT
                        break

                key2A = ''
                for keyT, value in frags['A'].items():
                    if len(keyT) > 4 and keyT[:4] == 'Link':
                        continue
                    if atom2A in value:
                        key2A = keyT
                        break

                key1B = ''
                for keyT, value in frags['B'].items():
                    if len(keyT) > 4 and keyT[:4] == 'Link':
                        continue
                    if atom1B in value:
                        key1B = keyT
                        break

                key2B = ''
                for keyT, value in frags['B'].items():
                    if len(keyT) > 4 and keyT[:4] == 'Link':
                        continue
                    if atom2B in value:
                        key2B = keyT
                        break

                vals[key][key1A][key1B] += V1A * V1B * energy
                vals[key][key1A][key2B] += V1A * V2B * energy
                vals[key][key2A][key1B] += V2A * V1B * energy
                vals[key][key2A][key2B] += V2A * V2B * energy

    return vals

def printOrder2(order2, fragkeys, saptkeys=saptkeys_):

    order1A = {}
    order1B = {}
    for saptkey in saptkeys:
        order1A[saptkey] = {}
        order1B[saptkey] = {}
        for keyA in fragkeys['A']:
            val = 0.0
            for keyB in fragkeys['B']:
                try:
                    val += order2[saptkey][keyA][keyB]
                except KeyError:
                    val += 0
            order1A[saptkey][keyA] = val
        for keyB in fragkeys['B']:
            val = 0.0
            for keyA in fragkeys['A']:
                try:
                    val += order2[saptkey][keyA][keyB]
                except KeyError:
                    val += 0.0
            order1B[saptkey][keyB] = val

    order0 = {}
    for saptkey in saptkeys:
        val = 0.0
        for keyA in fragkeys['A']:
            try:
                val += order1A[saptkey][keyA]
            except KeyError:
                val += 0.0
        order0[saptkey] = val

    print('%-9s %-9s ' % ('Frag1', 'Frag2'), end='')
    for saptkey in saptkeys:
        print('%8s ' % (saptkey), end='')
    print('')
    for keyA in fragkeys['A']:
        for keyB in fragkeys['B']:
            print('%-9s %-9s ' % (keyA, keyB), end='')
            for saptkey in saptkeys:
                if 'D3' in saptkey and ('Link' in keyA or 'Link' in keyB):
                    print('%8.3f' % 0.0, end='')
                else:
                    try:
                        print('%8.3f ' % (order2[saptkey][keyA][keyB]), end='')
                    except KeyError:
                        continue
            print('')

    for keyA in fragkeys['A']:
        print('%-9s %-9s ' % (keyA, 'All'), end='')
        for saptkey in saptkeys:
            print('%8.3f ' % (order1A[saptkey][keyA]), end='')
        print('')

    for keyB in fragkeys['B']:
        print('%-9s %-9s ' % ('All', keyB), end='')
        for saptkey in saptkeys:
            print('%8.3f ' % (order1B[saptkey][keyB]), end='')
        print('')

    print('%-9s %-9s ' % ('All', 'All'), end='')
    for saptkey in saptkeys:
        print('%8.3f ' % (order0[saptkey]), end='')
    print('')

    print('')

def diffOrder2(order2P, order2M):

    vals = {}
    for key in order2P.keys():
        vals[key] = {}
        for keyA in order2P[key].keys():
            vals[key][keyA] = {}
            for keyB in order2P[key][keyA].keys():
                vals[key][keyA][keyB] = order2P[key][keyA][keyB] - order2M[key][keyA][keyB]

    return vals

def computeFsapt(dirname, links5050, completeness = 0.85):

    geom = readXYZ('%s/geom.xyz' % dirname)

    Zs = {}
    Zs['A'] = readList('%s/ZA.dat' % dirname)
    Zs['B'] = readList('%s/ZB.dat' % dirname)

    holder = {}
    holder['A'] = readFrags('%s/fA.dat' % dirname)
    holder['B'] = readFrags('%s/fB.dat' % dirname)

    fragkeys = {}
    fragkeys['A'] = holder['A'][1]
    fragkeys['B'] = holder['B'][1]

    frags = {}
    frags['A'] = holder['A'][0]
    frags['B'] = holder['B'][0]

    checkFragments(geom, Zs['A'], frags['A'])
    checkFragments(geom, Zs['B'], frags['B'])

    Qs = {}
    Qs['A'] = readBlock('%s/QA.dat' % dirname)
    Qs['B'] = readBlock('%s/QB.dat' % dirname)

    holder1 = partitionFragments(fragkeys['A'], frags['A'], Zs['A'], Qs['A'], completeness)
    holder2 = partitionFragments(fragkeys['B'], frags['B'], Zs['B'], Qs['B'], completeness)

    fragkeysr = {}
    fragkeysr['A'] = fragkeys['A']
    fragkeysr['B'] = fragkeys['B']

    fragkeys['A'] = holder1[0]
    fragkeys['B'] = holder2[0]

    frags['A']    = holder1[1]
    frags['B']    = holder2[1]

    nuclear_ws = {}
    nuclear_ws['A'] = holder1[2]
    nuclear_ws['B'] = holder2[2]

    orbital_ws = {}
    orbital_ws['A'] = holder1[3]
    orbital_ws['B'] = holder2[3]

    total_ws = {}
    total_ws['A'] = holder1[4]
    total_ws['B'] = holder2[4]

    printFrag(geom, Zs['A'], Qs['A'], fragkeys['A'], frags['A'], nuclear_ws['A'], orbital_ws['A'], '%s/fragA.dat' % dirname)
    printFrag(geom, Zs['B'], Qs['B'], fragkeys['B'], frags['B'], nuclear_ws['B'], orbital_ws['B'], '%s/fragB.dat' % dirname)

    osapt = extractOsaptData(dirname)

    order2  = extractOrder2Fsapt(osapt, total_ws['A'], total_ws['B'], frags)
    order2r = collapseLinks(order2, frags, Qs, orbital_ws, links5050)
    order2r = buildOrder2FsaptD(order2r, fragkeysr)

    stuff = {}
    stuff['order2'] = order2
    stuff['fragkeys'] = fragkeys
    stuff['order2r'] = order2r
    stuff['fragkeysr'] = fragkeysr
    stuff['frags'] = frags
    stuff['geom'] = geom
    return stuff

# => Extra Order-2 Analysis <= #

class PDBAtom:

    def __init__(self, I, Z, x, y, z, T = 0.0):

        key_key        = 'HETATM'
        key_serial     = I
        key_name       = Z
        key_altLoc     = ''
        key_resName    = '001'
        key_chainID    = 'A'
        key_resSeq     = 1
        key_iCode      = ''
        key_x          = x
        key_y          = y
        key_z          = z
        key_occupancy  = 1.0
        key_tempFactor = T
        key_element    = Z
        key_charge     = 0

        self.key = key_key.strip()
        self.serial = int(key_serial)
        self.name = key_name.strip()
        self.altLoc = key_altLoc
        self.resName = key_resName.strip()
        self.chainID = key_chainID
        self.resSeq = int(key_resSeq)
        self.iCode = key_iCode
        self.x = float(key_x)
        self.y = float(key_y)
        self.z = float(key_z)
        self.occupancy = float(key_occupancy)
        self.tempFactor = float(key_tempFactor)
        self.element = key_element.strip()
        self.charge = int(key_charge)

    def __str__(self):

        if self.charge == 0:
            chargeStr = ''
        else:
            chargeStr = str(abs(self.charge))
            if self.charge > 0:
                chargeStr += '+'
            else:
                chargeStr += '-'

        return '%-6s%5d %-4s%1s%3s %1s%4d%1s   %8.3f%8.3f%8.3f%6.2f%6.2f          %2s%2s\n' % (self.key, self.serial, self.name, self.altLoc, self.resName, self.chainID, self.resSeq, self.iCode, self.x, self.y, self.z, self.occupancy, self.tempFactor, self.element, chargeStr)

    def xyzLine(self, form = '%8.3f '):
        contents = '%-2s ' + form + form + form + '\n'
        return contents % (self.element, self.x, self.y, self.z)

    def frozen(self):
        return atom_data_[self.element.upper()][2]

class PDB:

    def __init__(self, atoms, name):

        self.name = name
        self.atoms = atoms

    @classmethod
    def fromGeom(cls,geom):

        name = ''
        atoms = []

        for A in range(len(geom)):
            atoms.append(PDBAtom(
                A+1,
                geom[A][0],
                geom[A][1],
                geom[A][2],
                geom[A][3],
                ))

        return cls(atoms, name)

    def __str__(self):

        strval = '  --> PDB Object %s <--\n\n' % (self.name)
        for atom in self.atoms:
            strval += str(atom)
        strval += '\n'
        return strval

    def write(self,filename):
        fh = open(filename,'w')
        for atom in self.atoms:
            fh.write('%s' % str(atom))
        fh.close()

    def charge(self):
        charge = 0
        for atom in self.atoms:
            charge += atom.charge
        return charge

    def frozen(self):
        frozen = 0
        for atom in self.atoms:
            frozen += atom.frozen()
        return frozen

def printOrder1(dirname, order2, pdb, frags, reA = r'\S+', reB = r'\S+', saptkeys=saptkeys_):

    for saptkey in saptkeys:
        E = [0.0 for x in pdb.atoms]
        for keyA in order2[saptkey].keys():
            if not re.match(reA, keyA):
                continue
            for keyB in order2[saptkey][keyA].keys():
                if not re.match(reB, keyB):
                    continue
                val = order2[saptkey][keyA][keyB]
                for k in frags['A'][keyA]:
                    E[k] += val
                for l in frags['B'][keyB]:
                    E[l] += val

        pdb2 = copy.deepcopy(pdb)
        for A in range(len(pdb.atoms)):
            pdb2.atoms[A].tempFactor = E[A]
        pdb2.write('%s/%s.pdb' % (dirname, saptkey))

# => Driver Code <= #

if __name__ == '__main__':

    # > Working Dirname < #

    if len(sys.argv) == 1:
        dirname = '.'
    elif len(sys.argv) == 2:
        dirname = sys.argv[1]
    else:
        raise Exception('Usage: fsapt.py [dirname]')

    # > Order-2 Analysis < #

    fh = open('%s/fsapt.dat' % dirname, 'w')
    fh, sys.stdout = sys.stdout, fh

    print('  ==> F-ISAPT: Links by Charge <==\n')
    stuff = computeFsapt(dirname, False)
    print('   => Full Analysis <=\n')
    printOrder2(stuff['order2'], stuff['fragkeys'])
    print('   => Reduced Analysis <=\n')
    printOrder2(stuff['order2r'], stuff['fragkeysr'])

    print('  ==> F-ISAPT: Links 50-50 <==\n')
    stuff = computeFsapt(dirname, True)
    saptkeys_ = stuff['order2r'].keys()
    print('   => Full Analysis <=\n')
    printOrder2(stuff['order2'], stuff['fragkeys'])
    print('   => Reduced Analysis <=\n')
    printOrder2(stuff['order2r'], stuff['fragkeysr'])

    fh, sys.stdout = sys.stdout, fh
    fh.close()

    # > Order-1 PBD Files < #

    pdb = PDB.fromGeom(stuff['geom'])
    printOrder1(dirname, stuff['order2r'], pdb, stuff['frags'])
