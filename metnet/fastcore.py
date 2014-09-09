
'''Fastcore module implementing the fastcore algorithm

This is an implementation of the algorithms described in
Vlassis, Nikos, Maria Pires Pacheco, and Thomas Sauter.
"Fast reconstruction of compact context-specific metabolic
network models." PLoS computational biology 10.1 (2014):
e1003424.'''

import sys
import cplex

from . import lpsolver
from .fluxanalysis import flux_balance
from .metabolicmodel import FlipableModelView


def support(fluxiter, threshold=None):
    '''Yield reactions in the support set of the fluxes

    The fluxiter argument must be an iterable returning
    reaction, flux-pairs. The support set is the set of
    reactions that have an absolute flux value at or
    above a certain threshold. If threshold is None
    the mathematical definition (v != 0) is used.'''
    if threshold is None:
        return (rxnid for rxnid, v in fluxiter if v != 0)
    return (rxnid for rxnid, v in fluxiter if abs(v) >= threshold)

def support_positive(fluxiter, threshold=None):
    '''Yield reactions in the support set of the fluxes (only positive fluxes)

    The fluxiter argument must be an iterable returning
    reaction, flux-pairs. The support set is the set of
    reactions that have a flux value at or above a certain
    threshold. If threshold is None the mathematical
    definition (v > 0) is used.'''
    if threshold is None:
        return (rxnid for rxnid, v in fluxiter if v > 0)
    return (rxnid for rxnid, v in fluxiter if v >= threshold)


class Fastcore(object):
    '''Fastcore computation object containing reference to the solver'''

    def __init__(self, solver=lpsolver.CplexSolver()):
        self._solver = solver

    def _cpdid_str(self, compound):
        '''Create string identifier for compound with compartment'''
        cpdid, comp = compound
        if comp is None:
            return cpdid
        return cpdid+'_'+comp

    def lp7(self, model, reaction_subset, epsilon):
        # This is similar to FBA but approximately maximizing the number
        # of reactions in subset with flux > epsilon, instead of just
        # maximizing the flux of one particular reaction. LP7 prefers
        # "flux splitting" over "flux concentrating".

        # Create LP-7 problem of Fastcore
        prob = self._solver.create_problem()

        # Define flux variables
        for rxnid in model.reaction_set:
            lower, upper = model.limits[rxnid]
            prob.define('v_'+rxnid, lower=lower, upper=upper)

        # Define z variables
        prob.define(*('z_'+rxnid for rxnid in reaction_subset), lower=0, upper=epsilon)
        prob.set_linear_objective(sum(prob.var('z_'+rxnid) for rxnid in reaction_subset))
        v = prob.set('v_'+rxnid for rxnid in reaction_subset)
        z = prob.set('z_'+rxnid for rxnid in reaction_subset)
        prob.add_linear_constraints(v >= z)

        massbalance_lhs = { compound: 0 for compound in model.compound_set }
        for spec, value in model.matrix.iteritems():
            compound, rxnid = spec
            massbalance_lhs[compound] += prob.var('v_'+rxnid) * value
        prob.add_linear_constraints(*(lhs == 0 for compound, lhs in massbalance_lhs.iteritems()))

        # Solve
        prob.solve(lpsolver.CplexProblem.Maximize)
        status = prob.cplex.solution.get_status()
        if status != 1:
            raise Exception('Non-optimal solution: {}'.format(prob.cplex.solution.get_status_string()))

        for rxnid in sorted(model.reaction_set):
            yield rxnid, prob.get_value('v_'+rxnid)

    def lp10(self, model, subset_k, subset_p, epsilon, scaling, weights={}):
        # This program forces reactions in subset K to attain flux > epsilon
        # while minimizing the sum of absolute flux values for reactions
        # in subset P (L1-regularization).

        if len(subset_k) == 0:
            return

        # Create LP-10 problem of Fastcore
        prob = self._solver.create_problem()

        # Define flux variables
        for rxnid in model.reaction_set:
            lower, upper = model.limits[rxnid]
            if rxnid in subset_k:
                lower = max(lower, epsilon)
            prob.define('v_'+rxnid, lower=scaling*lower, upper=scaling*upper)

        # Define z variables
        prob.define(*('z_'+rxnid for rxnid in subset_p), lower=0)
        prob.set_linear_objective(sum(prob.var('z_'+rxnid) * weights.get(rxnid, 1) for rxnid in subset_p))

        z = prob.set('z_'+rxnid for rxnid in subset_p)
        v = prob.set('v_'+rxnid for rxnid in subset_p)
        prob.add_linear_constraints(z >= v, v >= -z)

        massbalance_lhs = { compound: 0 for compound in model.compound_set }
        for spec, value in model.matrix.iteritems():
            compound, rxnid = spec
            massbalance_lhs[compound] += prob.var('v_'+rxnid) * value
        prob.add_linear_constraints(*(lhs == 0 for compound, lhs in massbalance_lhs.iteritems()))

        # Solve
        prob.solve(lpsolver.CplexProblem.Minimize)
        status = prob.cplex.solution.get_status()
        if status != 1:
            raise Exception('Non-optimal solution: {}'.format(prob.cplex.solution.get_status_string()))

        for rxnid in sorted(model.reaction_set):
            yield rxnid, prob.get_value('v_'+rxnid)

    def fastcc(self, model, epsilon):
        '''Check consistency of model reactions

        Yields all reactions in the model that are not part
        of the consistent subset.'''

        reaction_set = set(model.reaction_set)
        subset = reaction_set - model.reversible
        #print '|J| = {}'.format(len(subset))
        #print 'J = {}'.format(subset)

        consistent_subset = set(support(self.lp7(model, subset, epsilon), epsilon))
        #print '|A| = {}'.format(len(consistent_subset))
        #print 'A = {}'.format(consistent_subset)

        for reaction in subset - consistent_subset:
            # Inconsistent reaction
            yield reaction

        # Check remaining reactions
        subset = (reaction_set - subset) - consistent_subset
        #print '|J| = {}'.format(len(subset))
        #print 'J = {}'.format(subset)

        # Wrap model in flipable proxy so reactions can be flipped
        model = FlipableModelView(model)

        flipped = False
        singleton = False
        while len(subset) > 0:
            if singleton:
                reaction = next(iter(subset))
                subset_i = { reaction }
                #print 'LP3 on {}'.format(subset_i)
                supp = support(flux_balance(model, reaction, self._solver), epsilon)
            else:
                subset_i = subset
                #print 'LP7 on {}'.format(subset_i)
                supp = support(self.lp7(model, subset_i, epsilon), epsilon)
            consistent_subset.update(supp)
            #print '|A| = {}'.format(len(consistent_subset))
            #print 'A = {}'.format(consistent_subset)

            if not subset.isdisjoint(consistent_subset):
                subset -= consistent_subset
                #print '|J| = {}'.format(len(subset))
                #print 'J = {}'.format(subset)
                flipped = False
            else:
                # TODO: irreversible reactions are taken care of before the
                # loop so at this point all reactions in subset_i are reversble(?).
                subset_rev_i = subset_i & model.reversible
                if flipped or len(subset_rev_i) == 0:
                    flipped = False
                    if singleton:
                        subset -= subset_rev_i
                        for reaction in subset_rev_i:
                            yield reaction
                    else:
                        singleton = True
                else:
                    model.flip(subset_rev_i)
                    flipped = True
                    #print 'Flip'

    def fastcc_is_consistent(self, model, epsilon):
        '''Quickly check whether model is consistent

        Returns true if the model is consistent. If it is only necessary
        to know whether a model is consistent, this function is faster
        as it will return the result as soon as it finds a single
        inconsistent reaction.'''
        for reaction in self.fastcc(model, epsilon):
            return False
        return True

    def fastcc_consistent_subset(self, model, epsilon):
        '''Return consistent subset of model

        The largest consistent subset is returned as
        a set of reaction names.'''
        reaction_set = set(model.reaction_set)
        return reaction_set.difference(self.fastcc(model, epsilon))

    def find_sparse_mode(self, model, core, additional, epsilon, weights={}):
        '''Find a sparse mode containing reactions of the core subset

        Return an iterator of the support of a sparse mode that contains as
        many reactions from core as possible, and as few reactions from additional
        as possible (approximately). A dictionary of weights can be supplied which
        gives further penalties for including specific additional reactions.'''

        if len(core) == 0:
            return iter(())

        supp = support_positive(self.lp7(model, core, epsilon), epsilon)
        k = core.intersection(supp)
        if len(k) == 0:
            return iter(())

        scaling = 1e5
        lp10_fluxes = dict(self.lp10(model, k, additional, epsilon, scaling=scaling, weights=weights))
        print 'LP10 (1)'
        for reaction, flux in sorted(lp10_fluxes.iteritems()):
            print '{}\t{}'.format(reaction, flux)

        prob = self._solver.create_problem()
        tol = prob.cplex.parameters.simplex.tolerances.feasibility
        print 'Tolerance: {}'.format(tol)

        # Define flux variables
        for rxnid in model.reaction_set:
            lower, upper = model.limits[rxnid]
            if abs(lp10_fluxes[rxnid]) < tol:
                lower, upper = 0, 0
            prob.define('v_'+rxnid, lower=lower, upper=upper)
            prob.define('z_'+rxnid, lower=0, upper=epsilon)

            if lp10_fluxes[rxnid] > tol:
                prob.add_linear_constraints(prob.var('v_'+rxnid) >= prob.var('z_'+rxnid))
            elif lp10_fluxes[rxnid] < -tol:
                prob.add_linear_constraints(-prob.var('v_'+rxnid) >= prob.var('z_'+rxnid))

        prob.set_linear_objective(sum(prob.var('z_'+rxnid) for rxnid in model.reaction_set))

        massbalance_lhs = { compound: 0 for compound in model.compound_set }
        for spec, value in model.matrix.iteritems():
            compound, rxnid = spec
            massbalance_lhs[compound] += prob.var('v_'+rxnid) * value
        prob.add_linear_constraints(*(lhs == 0 for compound, lhs in massbalance_lhs.iteritems()))

        # Solve
        prob.solve(lpsolver.CplexProblem.Maximize)
        status = prob.cplex.solution.get_status()
        if status != 1:
            raise Exception('Non-optimal solution: {}'.format(prob.cplex.solution.get_status_string()))

        print 'LPX'
        lpx_fluxes = { reaction:prob.get_value('v_'+reaction) for reaction in model.reaction_set }
        for reaction in sorted(model.reaction_set):
            if abs(lp10_fluxes[reaction]) > tol:
                print '{}\t{}'.format(reaction, lpx_fluxes[reaction])

        low_flux_reactions = set(reaction for reaction in model.reaction_set if abs(lp10_fluxes[reaction]) > tol and abs(lpx_fluxes[reaction]) < epsilon - tol)
        if len(low_flux_reactions) > 0:
            fluxes = { reaction: lpx_fluxes[reaction] for reaction in low_flux_reactions }
            raise Exception('Reactions unable to reach a flux of epsilon ({}): {}'.format(epsilon, fluxes))

        return (reaction for reaction in model.reaction_set if abs(lp10_fluxes[reaction]) > tol and abs(lpx_fluxes[reaction]) >= epsilon - tol)

    def fastcore(self, model, core, epsilon, weights={}):
        '''Find a flux consistent subnetwork containing the core subset

        The result will contain the core subset and as few of the additional
        reactions as possible.'''

        consistent_subset = set()
        reaction_set = set(model.reaction_set)

        subset = core - model.reversible
        #print '|J| = {}, J = {}'.format(len(subset), subset)
        #print '|J| = {}'.format(len(subset))

        penalty_set = reaction_set - core
        #print '|P| = {}, P = {}'.format(len(penalty_set), penalty_set)
        #print '|P| = {}'.format(len(penalty_set))

        mode = set(self.find_sparse_mode(model, subset, penalty_set, epsilon, weights=weights))
        if not subset.issubset(mode):
            raise Exception('Inconsistent irreversible core reactions: {}'.format(subset - mode))

        consistent_subset |= mode
        #print '|A| = {}, A = {}'.format(len(consistent_subset), consistent_subset)
        #print '|A| = {}'.format(len(consistent_subset))

        subset = core - mode
        #print '|J| = {}, J = {}'.format(len(subset), subset)
        #print '|J| = {}'.format(len(subset))

        # Wrap model in flipable proxy so reactions can be flipped
        model = FlipableModelView(model)

        flipped = False
        singleton = False
        while len(subset) > 0:
            penalty_set -= consistent_subset
            if singleton:
                subset_i = set((next(iter(subset)),))
            else:
                subset_i = subset

            mode = self.find_sparse_mode(model, subset_i, penalty_set, epsilon, weights=weights)
            consistent_subset.update(mode)
            #print '|A| = {}, A = {}'.format(len(consistent_subset), consistent_subset)
            #print '|A| = {}'.format(len(consistent_subset))

            if not subset.isdisjoint(consistent_subset):
                #print 'Subset improved {} -> {}'.format(len(subset), len(subset - consistent_subset))
                subset -= consistent_subset
                #print '|J| = {}, J = {}'.format(len(subset), subset)
                flipped = False
            else:
                #print 'Nothing found, changing state...'
                subset_rev_i = subset_i & model.reversible
                if flipped or len(subset_rev_i) == 0:
                    if singleton:
                        raise Exception('Global network inconsistent: {}'.format(subset_rev_i))

                    #print 'Going to non-flipped, singleton state...'
                    singleton = True
                    flipped = False
                else:
                    model.flip(subset_rev_i)
                    flipped = True
                    #print 'Going to flipped state... {}'.format(subset_rev_i)

        return consistent_subset
