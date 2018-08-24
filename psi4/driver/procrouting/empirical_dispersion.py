#
# @BEGIN LICENSE
#
# Psi4: an open-source quantum chemistry software package
#
# Copyright (c) 2007-2018 The Psi4 Developers.
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

import collections

import numpy as np

from psi4 import core
from psi4.driver import p4util
from psi4.driver.p4util.exceptions import ValidationError
from psi4.driver.qcdb import intf_dftd3
from psi4.driver.qcdb import interface_gcp as gcp

_engine_can_do = collections.OrderedDict([('libdisp', ['d1', 'd2', 'chg', 'das2009', 'das2010']),
                                          ('dftd3', ['d2', 'd3zero', 'd3bj', 'd3mzero', 'd3mbj']),
                                          ('nl', ['nl'])]) # yapf: disable

_capable_engines_for_disp = collections.defaultdict(list)
for eng, disps in _engine_can_do.items():
    for disp in disps:
        _capable_engines_for_disp[disp].append(eng)


class EmpiricalDispersion(object):
    """Lightweight unification of empirical dispersion calculation modes.

    Attributes
    ----------
    dashlevel: {'d1', 'd2', 'd3zero', 'd3bj', 'd3mzero', 'd3mbj', 'chg', 'das2009', 'das2010', 'nl'}
        Name of dispersion correction to be applied. Resolved
        from `name_hint` and/or `level_hint` into a key of
        `dashparam.dashcoeff`.
    dashparams : dict
        Complete (number and parameter names vary by `dashlevel`)
        set of parameter values defining the flexible parts
        of `dashlevel`. Resolved into a complete set (keys of
        dashcoeff[dashlevel]['default']) from `name_hint` and/or
        `dashcoeff_supplement` and/or user `param_tweaks`.
    fctldash : str
        If `dashparams` for `dashlevel` corresponds to a defined,
        named, untweaked "functional-dashlevel" set, then that
        functional. Otherwise, empty string.
    description : str
        Tagline for dispersion `dashlevel`.
    dashlevel_citation : str
        Literature reference for dispersion `dashlevel` in general,
        *not necessarily* for `dashparams`.
    dashcoeff_supplement : dict
        See description in `qcdb.intf_dftd3.dashparam.from_arrays`. Used
        here to "bless" the dispersion definitions attached
        to the procedures/dft_funcs-defined functional
        dictionaries as legit, non-custom, and of equal validity to
        `qcdb.intf_dftd3.dashparam.dashcoeff` itself for purposes of
        validating `fctldash`.
    engine : {'libdisp', 'dftd3', 'nl'}
        Compute engine for dispersion. One of Psi4's internal libdisp
        library, Grimme's DFTD3 executable, or nl.
    disp : psi4.core.Dispersion
        Only present for `engine=libdisp`. Psi4 class instance prepared
        to compute dispersion.
    ordered_params : list
        Fixed-order list of relevant parameters for `dashlevel`. Matches
        DFT_DISPERSION_PARAMETERS ordering. Used for printing.

    Parameters
    ----------
    name_hint : str, optional
        Name of functional (func only, func & disp, or disp only) for
        which to compute dispersion (e.g., blyp, BLYP-D2, blyp-d3bj,
        blyp-d3(bj), hf+d). Any or all parameters initialized from
        `dashcoeff[dashlevel][functional-without-dashlevel]` or
        `dashcoeff_supplement[dashlevel][functional-with-dashlevel]
        can be overwritten via `param_tweaks`.
    level_hint : str, optional
        Name of dispersion correction to be applied (e.g., d, D2,
        d3(bj), das2010). Must be key in `dashcoeff` or "alias" or
        "formal" to one.
    param_tweaks : list or dict, optional
        Values for the same keys as `dashcoeff[dashlevel]['default']`
        (and same order if list) used to override any or all values
        initialized by `name_hint`.  Extra parameters will error.
    engine : str, optional
        Override which code computes dispersion. See above for allowed
        values. Really only relevant for -D2, which can be computed by
        libdisp or dftd3.

    """

    def __init__(self, name_hint=None, level_hint=None, param_tweaks=None, **kwargs):
        from .dft_funcs import dashcoeff_supplement
        self.dashcoeff_supplement = dashcoeff_supplement

        resolved = intf_dftd3.from_arrays(
            name_hint=name_hint,
            level_hint=level_hint,
            param_tweaks=param_tweaks,
            dashcoeff_supplement=self.dashcoeff_supplement)
        self.fctldash = resolved['fctldash']
        self.dashlevel = resolved['dashlevel']
        self.dashparams = resolved['dashparams']
        self.description = intf_dftd3.dashcoeff[self.dashlevel]['description']
        self.ordered_params = intf_dftd3.dashcoeff[self.dashlevel]['default'].keys()
        self.dashlevel_citation = intf_dftd3.dashcoeff[self.dashlevel]['citation']

        engine = kwargs.pop('engine', None)
        if engine is None:
            self.engine = _capable_engines_for_disp[self.dashlevel][0]
        else:
            if self.dashlevel in _engine_can_do[engine]:
                self.engine = engine
            else:
                raise ValidationError("""This little engine ({}) can't ({})""".format(engine, self.dashlevel))

        if self.engine == 'libdisp':
            self.disp = core.Dispersion.build(self.dashlevel, **resolved['dashparams'])

    #    # 5) Override parameters from user input
    #    # 5a) pop citation if present
    #    if "citation" in kwargs:
    #        custom_citation = kwargs.pop("citation")
    #    else:
    #        custom_citation = False

    #    if len(kwargs):
    #        raise Exception("The following parameters in empirical_dispersion.py were not understood for %s dispersion type: %s" %
    #                        (dtype, ', '.join(kwargs.keys())))

    #    # 6) Process citations
    #    # 6a) Set default citations for method
    #    self.description = intf_dftd3.dashcoeff[self.dtype[1:]]['description']
    #    # 6b) add custom citations if available
    #    if custom_citation:
    #        self.citation += "\n    Parametrisation from: \n" + custom_citation

    def print_out(self):
        """Format dispersion parameters of `self` for output file."""

        core.print_out("   => %s: Empirical Dispersion <=\n\n" % self.fctldash.upper())
        core.print_out(self.description + "\n")

        # TODO core.print_out(self.citation + "\n\n")

        if self.engine == 'nl':
            return

        for op in self.ordered_params:
            core.print_out("    %6s = %14.6f\n" % (op, self.dashparams[op]))
        core.print_out("\n")

    def compute_energy(self, molecule):
        """Compute dispersion energy based on engine, dispersion level, and parameters in `self`.

        Parameters
        ----------
        molecule : psi4.core.Molecule
            System for which to compute empirical dispersion correction.

        Returns
        -------
        float
            Dispersion energy [Eh].

        """
        if self.engine == 'dftd3':
            jobrec = intf_dftd3.run_dftd3_from_arrays(
                molrec=molecule.to_dict(np_out=False),
                name_hint=self.fctldash,
                level_hint=self.dashlevel,
                param_tweaks=self.dashparams,
                dashcoeff_supplement=self.dashcoeff_supplement,
                ptype='energy',
                verbose=1)

            dashd_part = float(jobrec['qcvars']['DISPERSION CORRECTION ENERGY'].data)
            for k, qca in jobrec['qcvars'].items():
                if not isinstance(qca.data, np.ndarray):
                    core.set_variable(k, qca.data)

            if self.fctldash in ['hf3c', 'pbeh3c']:
                gcp_part = gcp.run_gcp(molecule, self.fctldash, verbose=False, dertype=0)
                dashd_part += gcp_part

            return dashd_part
        else:
            return self.disp.compute_energy(molecule)
            # TODO need to set 'DISPERSION CORRECTION ENERGY' and self.fctldash + 'DISPERSION CORRECTION ENERGY' psivars for libdisp?

    def compute_gradient(self, molecule):
        """Compute dispersion gradient based on engine, dispersion level, and parameters in `self`.

        Parameters
        ----------
        molecule : psi4.core.Molecule
            System for which to compute empirical dispersion correction.

        Returns
        -------
        psi4.core.Matrix
            (nat, 3) dispersion gradient [Eh/a0].

        """
        if self.engine == 'dftd3':
            jobrec = intf_dftd3.run_dftd3_from_arrays(
                molrec=molecule.to_dict(np_out=False),
                name_hint=self.fctldash,
                level_hint=self.dashlevel,
                param_tweaks=self.dashparams,
                dashcoeff_supplement=self.dashcoeff_supplement,
                ptype='gradient',
                verbose=1)

            dashd_part = core.Matrix.from_array(jobrec['qcvars']['DISPERSION CORRECTION GRADIENT'].data)
            for k, qca in jobrec['qcvars'].items():
                if not isinstance(qca.data, np.ndarray):
                    core.set_variable(k, qca.data)

            if self.fctldash in ['hf3c', 'pbeh3c']:
                gcp_part = gcp.run_gcp(molecule, self.fctldash, verbose=False, dertype=1)
                dashd_part.add(gcp_part)

            return dashd_part
        else:
            return self.disp.compute_gradient(molecule)

    def compute_hessian(self, molecule):
        """Compute dispersion Hessian based on engine, dispersion level, and parameters in `self`.
        Uses finite difference, as no dispersion engine has analytic second derivatives.

        Parameters
        ----------
        molecule : psi4.core.Molecule
            System for which to compute empirical dispersion correction.

        Returns
        -------
        psi4.core.Matrix
            (3*nat, 3*nat) dispersion Hessian [Eh/a0/a0].

        """
        optstash = p4util.OptionsState(['PRINT'])
        core.set_global_option('PRINT', 0)

        core.print_out("\n\n   Analytical Dispersion Hessians are not supported by dftd3 or gcp.\n")
        core.print_out("       Computing the Hessian through finite difference of gradients.\n\n")

        # Setup the molecule
        molclone = molecule.clone()
        molclone.reinterpret_coordentry(False)
        molclone.fix_orientation(True)
        molclone.fix_com(True)

        # Record undisplaced symmetry for projection of diplaced point groups
        core.set_parent_symmetry(molecule.schoenflies_symbol())

        gradients = []
        for geom in core.fd_geoms_freq_1(molecule, -1):
            molclone.set_geometry(geom)
            molclone.update_geometry()
            gradients.append(self.compute_gradient(molclone))

        H = core.fd_freq_1(molecule, gradients, -1)
        # H.print_out()
        optstash.restore()
        return H
