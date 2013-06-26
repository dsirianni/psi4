#ifndef EFP_SOLVER_H
#define EFP_SOLVER_H
/*
 * EFP header
 */

#include<libmints/molecule.h>

struct efp;

namespace psi{
  class Options;
}

namespace boost {
template<class T> class shared_ptr;
}

namespace psi{ 

class Vector;

namespace efp{


class EFP {
    // warning: options_ is pointer to current options object, and may not reflect
    // proper efp options outside of common_init()
    Options & options_;
    protected:
        int nfrag_;
        struct efp * efp_;
        boost::shared_ptr<Molecule>molecule_;
        bool elst_enabled_, pol_enabled_, disp_enabled_, exch_enabled_, do_grad_;
        /// Initialize options
        void common_init();
    public:
        EFP(Options& options);
        ~EFP();
        void set_options();

        /// Compute energy and/or gradient
        void Compute();

        /// Wrapper to efp_get_point_charge_gradient
        boost::shared_ptr<Vector> get_electrostatic_gradient();

        /// Designate which atoms are qm atoms.  This function is just a wrapper to efp_set_point_charges
        void set_qm_atoms();

        /// Returns EFP contribution to SCF energy
        double scf_energy_update();

        /// Returns EFP contribution to V
        boost::shared_ptr<Matrix> modify_Fock();

        /// Add potential files and names for all fragments
	    void add_fragments(std::vector<std::string> fnames);

        /// Add EFP fragment
        void add_fragment(std::string fname);

        /// Returns the number of EFP fragments
        int get_frag_count(void);
        
        /// Returns the number of atoms in specified fragment
        int get_frag_atom_count(int frag_idx);
        
        /// Returns atomic numbers of all atoms in a given fragment
        double *get_frag_atom_Z(int frag_idx);
        
        /// Returns masses of all atoms in a given fragment
        double *get_frag_atom_mass(int frag_idx);

        /// Returns the center of mass of a given fragment
        double *get_com(int frag_idx);

        /// Sets the geometry hints for all fragments at once
        void set_coordinates(int type, double * coords);

        /// Sets the geometry hints for a given fragment
        void set_frag_coordinates(int frag_idx, int type, double * coords);

        /// Returns xyz coordinates of all atoms in a given fragment
        double *get_frag_atom_coord(int frag_idx);

        /// Returns atom label of all atoms in a given fragment
        std::vector<std::string> get_frag_atom_label(int frag_idx);

        /// Print all of the EFP atoms
        void print_efp_geometry();

        /// Number of EFP atoms
        int efp_natom();

        /// Returns charge for a given fragment
        double get_frag_charge(int frag_idx);

        /// Returns multiplicity for a given fragment
        int get_frag_multiplicity(int frag_idx);

        /// Prints private members of efp object
        void print_out(void);

        /// Computes the nuclear repulsion between the QM and EFP regions
        double EFP_QM_nuclear_repulsion_energy();


};

}
}

#endif
