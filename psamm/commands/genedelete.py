# This file is part of PSAMM.
#
# PSAMM is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# PSAMM is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with PSAMM.  If not, see <http://www.gnu.org/licenses/>.
#
# Copyright 2014-2015  Jon Lund Steffensen <jon_steffensen@uri.edu>
# Copyright 2015  Keith Dufault-Thompson <keitht547@my.uri.edu>

from __future__ import unicode_literals

import time
import logging

from ..command import (Command, MetabolicMixin, SolverCommandMixin,
                       CommandError, FilePrefixAppendAction)
from .. import fluxanalysis
from ..expression import boolean

from six import string_types

logger = logging.getLogger(__name__)


class GeneDeletionCommand(MetabolicMixin, SolverCommandMixin, Command):
    """Find reactions requiring a spcified gene and delete them from model
    """
    @classmethod
    def init_parser(cls, parser):
        parser.add_argument(
            '--gene', metavar='genes', action=FilePrefixAppendAction,
            type=str, default=[], help='Delete Multiple Genes From Model')
        parser.add_argument('--objective', help='Reaction flux to maximize')
        super(GeneDeletionCommand, cls).init_parser(parser)

    def run(self):
        if self._args.objective is not None:
            obj_reaction = self._args.objective
        else:
            obj_reaction = self._model.get_biomass_reaction()
            if obj_reaction is None:
                raise CommandError('The biomass reaction was not specified')
        logger.info('Running single gene deletion...')
        genes = set()
        gene_assoc = {}
        for reaction in self._model.parse_reactions():
            assoc = None
            if reaction.genes is None:
                continue
            elif isinstance(reaction.genes, string_types):
                assoc = boolean.Expression(reaction.genes)
            else:
                variables = [boolean.Variable(g) for g in reaction.genes]
                assoc = boolean.Expression(boolean.And(*variables))
            genes.update(v.symbol for v in assoc.variables)
            gene_assoc[reaction.id] = assoc

        reactions = set(self._mm.reactions)
        start_time = time.time()
        testing_genes = set(self._args.gene)
        deleted_reactions = set()

        logger.info('Trying model without gene {}...'.format(
                    testing_genes))

        for reaction in reactions:
            if reaction not in gene_assoc:
                continue
            assoc = gene_assoc[reaction]
            found = False
            for gene in testing_genes:
                if boolean.Variable(gene) in assoc.variables:
                    found = True
                    break
            if found:
                new_assoc = assoc.substitute(
                    lambda v: v if v.symbol not in testing_genes else False)
                if new_assoc.has_value() and not new_assoc.value:
                    logger.info('Deletion reaction {}...'.format(reaction))
                    deleted_reactions.add(reaction)

        print (deleted_reactions)
        solver = self._get_solver()
        prob = fluxanalysis.FluxBalanceProblem(self._mm, solver)

        flux_var = prob.get_flux_var(reaction)
        prob.prob.add_linear_constraints(flux_var == 0)
        prob.maximize(obj_reaction)
        prob.get_flux(obj_reaction)
        wild = prob.get_flux(obj_reaction)

        for reaction in deleted_reactions:
            flux_var = prob.get_flux_var(reaction)
            prob.prob.add_linear_constraints(flux_var == 0)
            prob.maximize(obj_reaction)
            prob.get_flux(obj_reaction)
        deleteflux = prob.get_flux(obj_reaction)
        logger.info('Solving took {:.2f} seconds'.format(
            time.time() - start_time))
        logger.info('Reaction {} has flux {}'.format(
            obj_reaction, prob.get_flux(obj_reaction)))
        logger.info('Reaction {} has {} %  flux of wild type flux'.format(
            obj_reaction, ((deleteflux / wild) * 100)))
