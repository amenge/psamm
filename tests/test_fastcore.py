#!/usr/bin/env python

import unittest

from metnet import metabolicmodel
from metnet import fastcore
from metnet import lpsolver
from metnet.reaction import ModelSEED

class TestFastcoreSimpleVlassisModel(unittest.TestCase):
    '''Test fastcore using the simple model in Vlassis et al. 2014.'''

    def setUp(self):
        # TODO use mock model instead of actual model
        self.database = metabolicmodel.MetabolicDatabase()
        self.database.set_reaction('rxn_1', ModelSEED.parse('=> (2) |A|'))
        self.database.set_reaction('rxn_2', ModelSEED.parse('|A| <=> |B|'))
        self.database.set_reaction('rxn_3', ModelSEED.parse('|A| => |D|'))
        self.database.set_reaction('rxn_4', ModelSEED.parse('|A| => |C|'))
        self.database.set_reaction('rxn_5', ModelSEED.parse('|C| => |D|'))
        self.database.set_reaction('rxn_6', ModelSEED.parse('|D| =>'))
        self.model = self.database.get_model(self.database.reactions)
        self.fastcore = fastcore.Fastcore(lpsolver.CplexSolver(None))

    def test_lp10(self):
        result = self.fastcore.lp10(self.model, { 'rxn_6' }, { 'rxn_1', 'rxn_3', 'rxn_4', 'rxn_5' }, 0.001)
        supp = set(fastcore.support(result))
        self.assertEqual(supp, { 'rxn_1', 'rxn_3', 'rxn_6' })

    def test_lp10_weighted(self):
        weights = { 'rxn_3': 1 }
        result = self.fastcore.lp10(self.model, { 'rxn_6' }, { 'rxn_1', 'rxn_3', 'rxn_4', 'rxn_5' }, 0.001,
                                    weights=weights)
        supp = set(fastcore.support(result))
        self.assertEqual(supp, { 'rxn_1', 'rxn_3', 'rxn_6' })

        weights = { 'rxn_3': 3 }
        result = self.fastcore.lp10(self.model, { 'rxn_6' }, { 'rxn_1', 'rxn_3', 'rxn_4', 'rxn_5' }, 0.001,
                                    weights=weights)
        supp = set(fastcore.support(result))
        self.assertEqual(supp, { 'rxn_1', 'rxn_4', 'rxn_5', 'rxn_6' })

    def test_lp7(self):
        result = self.fastcore.lp7(self.model, set(self.model.reaction_set), 0.001)
        supp = set(fastcore.support_positive(result, 0.001*0.99))
        self.assertEqual(supp, { 'rxn_1', 'rxn_3', 'rxn_4', 'rxn_5', 'rxn_6' })

        result = self.fastcore.lp7(self.model, {'rxn_5'}, 0.001)
        supp = set(fastcore.support_positive(result, 0.001*0.99))
        self.assertEqual(supp, { 'rxn_1', 'rxn_4', 'rxn_5', 'rxn_6' })

    def test_find_sparse_mode_singleton(self):
        core = { 'rxn_1' }
        mode = set(self.fastcore.find_sparse_mode(self.model, core, set(self.model.reaction_set) - core, 0.001))
        self.assertEqual(mode, { 'rxn_1', 'rxn_3', 'rxn_6' })

        core = { 'rxn_2' }
        mode = set(self.fastcore.find_sparse_mode(self.model, core, set(self.model.reaction_set) - core, 0.001))
        self.assertEqual(mode, set())

        core = { 'rxn_3' }
        mode = set(self.fastcore.find_sparse_mode(self.model, core, set(self.model.reaction_set) - core, 0.001))
        self.assertEqual(mode, { 'rxn_1', 'rxn_3', 'rxn_6' })

        core = { 'rxn_4' }
        mode = set(self.fastcore.find_sparse_mode(self.model, core, set(self.model.reaction_set) - core, 0.001))
        self.assertEqual(mode, { 'rxn_1', 'rxn_4', 'rxn_5', 'rxn_6' })

        core = { 'rxn_5' }
        mode = set(self.fastcore.find_sparse_mode(self.model, core, set(self.model.reaction_set) - core, 0.001))
        self.assertEqual(mode, { 'rxn_1', 'rxn_4', 'rxn_5', 'rxn_6' })

        core = { 'rxn_6' }
        mode = set(self.fastcore.find_sparse_mode(self.model, core, set(self.model.reaction_set) - core, 0.001))
        self.assertEqual(mode, { 'rxn_1', 'rxn_3', 'rxn_6' })

    def test_find_sparse_mode_weighted(self):
        core = { 'rxn_1' }
        weights = { 'rxn_3': 1 }
        mode = set(self.fastcore.find_sparse_mode(self.model, core, set(self.model.reaction_set) - core,
                                                    0.001, weights=weights))
        self.assertEqual(mode, { 'rxn_1', 'rxn_3', 'rxn_6' })

        weights = { 'rxn_3': 3 }
        mode = set(self.fastcore.find_sparse_mode(self.model, core, set(self.model.reaction_set) - core,
                                                    0.001, weights=weights))
        self.assertEqual(mode, { 'rxn_1', 'rxn_4', 'rxn_5', 'rxn_6' })

    def test_fastcc_inconsistent(self):
        self.assertEqual(set(self.fastcore.fastcc(self.model, 0.001)), { 'rxn_2' })

    def test_fastcc_is_consistent_on_inconsistent(self):
        self.assertFalse(self.fastcore.fastcc_is_consistent(self.model, 0.001))

    def test_fastcc_is_consistent_on_consistent(self):
        self.model.remove_reaction('rxn_2')
        self.assertTrue(self.fastcore.fastcc_is_consistent(self.model, 0.001))

    def test_fastcc_consistent_subset(self):
        self.assertEqual(self.fastcore.fastcc_consistent_subset(self.model, 0.001), set(['rxn_1', 'rxn_3', 'rxn_4', 'rxn_5', 'rxn_6']))

    def test_fastcore_global_inconsistent(self):
        self.database.set_reaction('rxn_7', ModelSEED.parse('|E| <=>'))
        with self.assertRaises(Exception):
            self.fastcore.fastcore(self.model, { 'rxn_7' }, 0.001)

class TestFastcoreTinyBiomassModel(unittest.TestCase):
    '''Test fastcore using a model with tiny values in objective reaction

    This model is consistent mathematically since there is a flux solution
    within the flux bounds. However, the numerical nature of the fastcore
    algorithm requires an epsilon-parameter indicating the minimum flux that
    is considered non-zero. For this reason, some models with reactions where
    tiny stoichiometric values appear can be seen as inconsistent by
    fastcore.

    In this particular model, rxn_2 can take a maximum flux of 1000. At the
    same time rxn_1 will have to take a flux of 1e-4. This is the maximum
    possible flux for rxn_1 so running fastcore with an epsilon larger than
    1e-4 will indicate that the model is not consistent.'''

    def setUp(self):
        # TODO use mock model instead of actual model
        self.database = metabolicmodel.MetabolicDatabase()
        self.database.set_reaction('rxn_1', ModelSEED.parse('=> |A|')) # v=1e-4
        self.database.set_reaction('rxn_2', ModelSEED.parse('(0.0000001) |A| =>')) # v=1000
        self.model = self.database.get_model(self.database.reactions)
        self.fastcore = fastcore.Fastcore(lpsolver.CplexSolver(None))

    def test_fastcc_is_consistent(self):
        self.assertTrue(self.fastcore.fastcc_is_consistent(self.model, 1e-5))

    def test_fastcore_induced_model(self):
        core = { 'rxn_2' }
        self.assertEquals(set(self.fastcore.fastcore(self.model, core, 1e-5)), { 'rxn_1', 'rxn_2' })

    def test_fastcc_is_not_consistent(self):
        self.assertFalse(self.fastcore.fastcc_is_consistent(self.model, 1e-3))

    def test_fastcore_induced_model_inconsistent(self):
        core = { 'rxn_2' }
        with self.assertRaises(Exception):
            self.fastcore.fastcore(self.model, core, 1e-3)

class TestFlippingModel(unittest.TestCase):
    '''Test fastcore on a model that has to flip'''

    def setUp(self):
        # TODO use mock model instead of actual model
        self.database = metabolicmodel.MetabolicDatabase()
        self.database.set_reaction('rxn_1', ModelSEED.parse('|A| <=>'))
        self.database.set_reaction('rxn_2', ModelSEED.parse('|A| <=> |B|'))
        self.database.set_reaction('rxn_3', ModelSEED.parse('|C| <=> |B|'))
        self.database.set_reaction('rxn_4', ModelSEED.parse('|C| <=>'))
        self.model = self.database.get_model(self.database.reactions)
        self.fastcore = fastcore.Fastcore(lpsolver.CplexSolver(None))

    def test_fastcore_induced_model(self):
        core = { 'rxn_2', 'rxn_3' }
        self.assertEquals(set(self.fastcore.fastcore(self.model, core, 0.001)),
                            { 'rxn_1', 'rxn_2', 'rxn_3', 'rxn_4' })

if __name__ == '__main__':
    unittest.main()
