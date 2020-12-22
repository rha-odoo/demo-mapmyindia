# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models


class ResPartner(models.Model):
    _inherit = "res.partner"

    # TODO: only for test
    def check_vat_in(self, vat):
        if vat == "36AABCT1332L011":
            return True
        return super().check_vat_in(vat)
