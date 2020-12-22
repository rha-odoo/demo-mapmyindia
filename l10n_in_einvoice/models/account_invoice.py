# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import re

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountInvoice(models.Model):
    _inherit = "account.invoice"

    l10n_in_transaction_id = fields.Many2one(
        "l10n.in.einvoice.transaction", "GSTN Transaction", copy=False
    )
    l10n_in_transaction_status = fields.Selection(
        related="l10n_in_transaction_id.status", string="GSTN Transaction Status"
    )
    tax_rate_by_lines = fields.Binary(
        string="Tax rate for lines",
        compute="_compute_invoice_taxes_rate_by_line_by_group",
        help="Tax rate by group for the invoice line.",
    )

    l10n_in_export_type = fields.Selection([
        ('regular', 'Regular'), ('deemed', 'Deemed'),
        ('sale_from_bonded_wh', 'Sale from Bonded WH'),
        ('export_with_igst', 'Export with IGST'),
        ('sez_with_igst', 'SEZ with IGST payment'),
        ('sez_without_igst', 'SEZ without IGST payment')],
        string='Export Type', default='regular', required=True)
    l10n_in_extend_state_id = fields.Many2one(
        'res.country.state', string="Location of supply"
    )

    def _compute_invoice_taxes_rate_by_line_by_group(self):
        for invoice in self:
            taxes = {}
            for line in invoice.invoice_line_ids:
                taxes[line.id] = line.tax_rate_by_tax_group
            invoice.tax_rate_by_lines = taxes

    def _extract_digits(self, string):
        matches = re.findall(r"\d+", string)
        result = "".join(matches)
        return result

    def _validate_invoice_data(self):
        self.ensure_one()

        message = ''
        if not self.number or not re.match("^.{1,16}$", self.number):
            message += "\n- Invoice number should not be more than 16 charactor"
        for line in self.invoice_line_ids:
            if line.product_id and (
                not line.product_id.l10n_in_hsn_code
                or not re.match("^[0-9]+$", line.product_id.l10n_in_hsn_code)
            ):
                message += "\n- HSN code required for product %s" % (
                    line.product_id.name
                )

        if message:
            raise UserError(
                "Data not valid for the Invoice: %s\n%s" % (self.number, message)
            )

    def _validate_legal_identity_data(self, partner, is_company=False):
        self.ensure_one()

        message = ''
        if not partner:
            raise UserError("Error: Customer not found!")
        if is_company and partner.country_id.code != "IN":
            message += "\n- Country should be India"
        if not re.match("^.{3,100}$", partner.street or ""):
            message += "\n- Street required min 3 and max 100 charactor"
        if partner.street2 and not re.match("^.{3,100}$", partner.street2):
            message += "\n- Street2 should be min 3 and max 100 charactor"
        if not re.match("^.{3,100}$", partner.city or ""):
            message += "\n- City required min 3 and max 100 charactor"
        if not re.match("^.{3,50}$", partner.state_id.name or ""):
            message += "\n- State required min 3 and max 50 charactor"
        if partner.country_id.code == "IN" and not re.match(
            "^[0-9]{6,}$", partner.zip or ""
        ):
            message += "\n- Zip code required 6 digites"
        if partner.phone and not re.match(
            "^[0-9]{10,12}$", self._extract_digits(partner.phone)
        ):
            message += "\n- Phone number should be minimum 10 or maximum 12 digites"
        if partner.email and (
            not re.match(
                r"^\w+([\.-]?\w+)*@\w+([\.-]?\w+)*(\.\w{2,3})+$", partner.email
            )
            or not re.match("^.{3,100}$", partner.email)
        ):
            message += (
                "\n- Email address should be valid and not more then 100 charactor"
            )

        if not is_company:
            # TODO: check customer specific details
            pass

        if message:
            raise UserError(
                "Data not valid for the %s: %s\n%s"
                % (is_company and "Company" or "Customer", partner.name, message)
            )

    def button_l10n_in_submit_einvoice(self):
        self.ensure_one()

        if self.state in ("draft", "cancel"):
            raise UserError(_("You can submit only confirmed invoice to GSTN Portal"))

        customer = self.partner_id

        self._validate_invoice_data()
        self._validate_legal_identity_data(self.journal_id.company_id.partner_id, is_company=True)
        self._validate_legal_identity_data(customer)

        transaction = self.env["l10n.in.einvoice.transaction"]
        transaction = transaction.sudo().create({"invoice_id": self.id})
        self.l10n_in_transaction_id = transaction.id
        transaction.submit_invoice()

    def button_l10n_in_cancel_einvoice(self):
        self.ensure_one()
        if self.state != "cancel":
            raise UserError(_("You cannot cancel IRN from %s state" % (self.state)))
        return self.env.ref(
            "l10n_in_einvoice.l10n_in_einvoice_cancel_wizard_action"
        ).read()[0]

    @api.model
    def _l10n_in_get_indian_state(self, partner):
        """In tax return filing, If customer is not Indian in that case place of supply is must set to Other Territory.
        So we set Other Territory in l10n_in_extend_state_id when customer(partner) is not Indian
        Also we raise if state is not set in Indian customer.
        State is big role under GST because tax type is depend on.for more information check this https://www.cbic.gov.in/resources//htdocs-cbec/gst/Integrated%20goods%20&%20Services.pdf"""
        if partner.country_id and partner.country_id.code == 'IN' and not partner.state_id:
            raise ValidationError(_("State is missing from address in '%s'. First set state after post this invoice again." %(partner.name)))
        elif partner.country_id and partner.country_id.code != 'IN':
            return self.env.ref('l10n_in_extend.state_in_oc')
        return partner.state_id

    @api.multi
    def action_invoice_open(self):
        res = super().action_invoice_open()

        """Use journal type to define document type because not miss state in any entry including POS entry"""
        for invoice in self.filtered(lambda m: m.company_id.country_id.code == 'IN'):
            """Check state is set in company/sub-unit"""
            company_unit_partner = invoice.journal_id.company_id
            if not company_unit_partner.state_id:
                raise ValidationError(_("State is missing from your company/unit %s(%s).\nFirst set state in your company/unit." % (company_unit_partner.name, company_unit_partner.id)))
            elif self.journal_id.type == 'purchase':
                invoice.l10n_in_extend_state_id = company_unit_partner.state_id

            shipping_partner = shipping_partner = ('partner_shipping_id' in self) and self.partner_shipping_id or self.partner_id
            if self.journal_id.type == 'sale':
                invoice.l10n_in_extend_state_id = self._l10n_in_get_indian_state(shipping_partner)
                if not invoice.l10n_in_extend_state_id:
                    invoice.l10n_in_extend_state_id = self._l10n_in_get_indian_state(invoice.partner_id)
                #still state is not set then assumed that transaction is local like PoS so set state of company unit
                if not invoice.l10n_in_extend_state_id:
                    invoice.l10n_in_extend_state_id = company_unit_partner.state_id
        return res

class AccountInvoiceLine(models.Model):
    _inherit = "account.invoice.line"

    tax_rate_by_tax_group = fields.Binary(
        string="Tax rate by group",
        compute="_compute_invoice_line_tax_rate_by_group",
        help="Tax rate by group for the line.",
    )

    def _compute_invoice_line_tax_rate_by_group(self):
        for line in self:
            invoice = line.invoice_id
            taxes = {}
            for ln in invoice.tax_line_ids.filtered(lambda l: l.l10n_in_invoice_line_id == line):
                tax_group_name = ln.tax_id.tax_group_id.name.upper()
                taxes.setdefault(tax_group_name, 0.0)
                taxes[tax_group_name] += ln.tax_id.amount
            line.tax_rate_by_tax_group = taxes


class AccountTax(models.Model):
    _inherit = 'account.tax'

    l10n_in_reverse_charge = fields.Boolean("Reverse charge", help="Tick this if this tax is reverse charge. Only for Indian accounting")


class ProductUoM(models.Model):
    _inherit = 'product.uom'

    # As per GST Rules you need to Specify UQC given by GST.
    l10n_in_code = fields.Char("Indian GST UQC", help="Unique Quantity Code (UQC) under GST")
