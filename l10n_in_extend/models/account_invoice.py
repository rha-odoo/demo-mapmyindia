# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    l10n_in_shipping_bill_number = fields.Char('Shipping bill number', readonly=True, states={'draft': [('readonly', False)]})
    l10n_in_shipping_bill_date = fields.Date('Shipping bill date', readonly=True, states={'draft': [('readonly', False)]})
    l10n_in_shipping_port_code = fields.Char('Shipping port code', states={'draft': [('readonly', False)]})
    # Use for invisible fields in form views.
    l10n_in_import_export = fields.Boolean(
       related='journal_id.l10n_in_import_export', readonly=True
    )
    tax_amount_by_lines = fields.Binary(string='Tax amount for lines',
        compute='_compute_invoice_taxes_by_line_by_group',
        help='Tax amount by group for the invoice line.')
    l10n_in_export_type = fields.Selection([
        ('regular', 'Regular'), ('deemed', 'Deemed'),
        ('sale_from_bonded_wh', 'Sale from Bonded WH'),
        ('export_with_igst', 'Export with IGST'),
        ('sez_with_igst', 'SEZ with IGST payment'),
        ('sez_without_igst', 'SEZ without IGST payment')],
        string='Export Type', default='regular', required=True)


    @api.depends('invoice_line_ids')
    def _compute_invoice_taxes_by_line_by_group(self):
        for invoice in self:
            taxes = {}
            for line in invoice.invoice_line_ids:
                taxes[str(line.id)] = line.tax_amount_by_tax_group
            invoice.tax_amount_by_lines = taxes

    def _prepare_tax_line_vals(self, line, tax):
        res = super()._prepare_tax_line_vals(line, tax)
        res.update({
            'l10n_in_invoice_line_ref': line.id,
            'l10n_in_invoice_line_id': line.id
        })
        return res

    @api.multi
    def action_invoice_open(self):
        # explicitely calling onchange to trigger recomputation of tax_line_ids, which, in-turn, will
        # help to set l10n_in_invoice_line_id with real ID
        self._onchange_invoice_line_ids()
        return super().action_invoice_open()


class AccountInvoiceLine(models.Model):
    _inherit = 'account.invoice.line'

    tax_amount_by_tax_group = fields.Binary(string='Tax amount by group',
        compute='_compute_invoice_line_taxes_by_group',
        help='Tax amount by group for the line.')

    def _compute_invoice_line_taxes_by_group(self):
        # prepare the dict of tax values by tax group
        # line.tax_amount_by_tax_group = {'SGST': 9.0, 'CGST': 9.0, 'Cess': 2.0}
        for line in self:
            invoice = line.invoice_id
            invoice_type = invoice.type in ('out_invoice', 'in_refund') and 'outbound' or 'inbound'
            taxes = {}
            for tax_line in invoice.tax_line_ids.filtered(lambda l: l.l10n_in_invoice_line_id == line):
                tax_group_name = tax_line.tax_id.tax_group_id.name.upper()
                if tax_group_name not in ('SGST', 'CGST', 'IGST', 'CESS', 'CESS-NON-ADVOL','STATE CESS','STATE CESS-NON-ADVOL'):
                    tax_group_name = 'OTHER'
                taxes.setdefault(tax_group_name, 0.0)
                taxes[tax_group_name] += tax_line.amount_total * (invoice_type == 'inbound' and -1 or 1)
            line.tax_amount_by_tax_group = taxes


class AccountInvoiceTax(models.Model):
    _inherit = "account.invoice.tax"

    l10n_in_invoice_line_id = fields.Many2one('account.invoice.line', 'Invoice Line')
    l10n_in_invoice_line_ref = fields.Char('Invoice Line Reference')

    @api.depends('invoice_id.invoice_line_ids')
    def _compute_base_amount(self):
        if self.mapped('company_id.country_id.code')[0] != 'IN':
            super()._compute_base_amount()
        else:
            tax_grouped = {}
            for invoice in self.mapped('invoice_id'):
                tax_grouped[invoice.id] = invoice.get_taxes_values()
            for tax in self:
                tax.base = 0.0
                if tax.tax_id:
                    key = tax.tax_id.get_grouping_key({
                        'tax_id': tax.tax_id.id,
                        'account_id': tax.account_id.id,
                        'account_analytic_id': tax.account_analytic_id.id,
                        'l10n_in_invoice_line_ref': tax.l10n_in_invoice_line_id.id,
                    })
                    if tax.invoice_id and key in tax_grouped[tax.invoice_id.id]:
                        tax.base = tax_grouped[tax.invoice_id.id][key]['base']
                    else:
                        _logger.warning('Tax Base Amount not computable probably due to a change in an underlying tax (%s).', tax.tax_id.name)


class AccountTax(models.Model):
    _inherit = 'account.tax'

    def get_grouping_key(self, invoice_tax_val):
        """ Returns a string that will be used to group account.invoice.tax sharing the same properties"""
        self.ensure_one()
        if self.company_id.country_id.code != 'IN':
            return super().get_grouping_key(invoice_tax_val)
        return str(invoice_tax_val.get('l10n_in_invoice_line_ref', '')) + '-' + \
               str(invoice_tax_val['tax_id']) + '-' + \
               str(invoice_tax_val['account_id']) + '-' + \
               str(invoice_tax_val['account_analytic_id'])
