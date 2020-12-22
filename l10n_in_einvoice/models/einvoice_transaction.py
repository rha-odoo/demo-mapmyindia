# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import json
import re

from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import RedirectWarning
from odoo.tools.safe_eval import safe_eval


class L10nInInvoiceTransaction(models.Model):
    _name = 'l10n.in.einvoice.transaction'
    _description = 'India eInvoice Transaction'
    _rec_name ="ack_no"

    invoice_id = fields.Many2one('account.invoice', 'Invoice')
    irn = fields.Char('IRN', help='Invoice Registration Number (IRN)', compute="_get_data_from_response_json")
    ack_no = fields.Char('Ack No', compute="_get_data_from_response_json")
    ack_date = fields.Char('Ack Date', compute="_get_data_from_response_json")
    qr_code_data = fields.Char('QR Code', compute="_get_data_from_response_json")
    generation_datatime = fields.Datetime("Generation time", compute="_get_data_from_response_json")
    status = fields.Selection([('submitted', 'Submitted'),
                                ('cancel', 'Cancelled'),
                                ], string='Status')
    generate_request_json = fields.Text(
        compute='_compute_generate_request_json', string='Request', store=True)
    response_json = fields.Text('Response', default='{}')

    cancellation_datatime = fields.Datetime("Cancellation time")
    cancel_reason = fields.Selection([('1','Duplicate'),('2','Data Entry Mistake')],
        string='Cancel reason',)
    cancel_remarks = fields.Char('Cancel Remarks')
    cancel_request_json = fields.Text(
        compute='_compute_cancel_request_json', string='Cancel request', store=True)
    cancel_response_json = fields.Text('Cancel response')

    @api.depends('response_json')
    def _get_data_from_response_json(self):
        for transaction in self:
            response_json_dir = json.loads(transaction.response_json)
            transaction.irn = response_json_dir.get('Irn')
            transaction.ack_no = response_json_dir.get('AckNo')
            transaction.ack_date = response_json_dir.get('AckDt')
            transaction.qr_code_data = response_json_dir.get('SignedQRCode')
            if response_json_dir.get('AckDt'):
                transaction.generation_datatime = fields.Datetime.from_string(response_json_dir.get('AckDt')) - timedelta(hours=5, minutes=30, seconds=00)
            else:
                transaction.generation_datatime = False

    @api.model
    def _get_supply_type(self, invoice):
        supply_type = 'B2B'
        if invoice.l10n_in_import_export:
            if invoice.l10n_in_export_type == 'regular':
                supply_type = "EXPWOP"
            if invoice.l10n_in_export_type == 'export_with_igst':
                supply_type = "EXPWP"
            if invoice.l10n_in_export_type == 'sez_with_igst':
                supply_type = 'SEZWP'
            if invoice.l10n_in_export_type == 'sez_without_igst':
                supply_type = "SEZWOP"
            if invoice.l10n_in_export_type == 'deemed':
                supply_type = "DEXP"
            # TODO: sale_from_bonded_wh
        return supply_type

    def _extract_digits(self, number):
        if number:
            matches = re.findall(r'\d+', number)
            return "".join(matches)
        return False

    def get_amount_by_group(self):
        values = {}
        for tax_line in self.invoice_id.tax_line_ids:
            key_of_group = tax_line.tax_id.tax_group_id and tax_line.tax_id.tax_group_id.name.upper() or False
            values.setdefault(key_of_group, 0.00)
            values[key_of_group] += tax_line.amount_total
        return values

    def get_round_off_value(self, invoice):
        return sum(invoice.invoice_line_ids.filtered(lambda l: l.is_rounding_line).mapped('price_subtotal'))

    def get_amount_in_INR(self, amount):
        if self.invoice_id.currency_id and self.invoice_id.company_id.currency_id != self.invoice_id.currency_id:
            rate_date = self.invoice_id._get_currency_rate_date() or fields.Date.today()
            amount_in_inr = self.invoice_id.currency_id._convert(amount, self.invoice_id.company_id.currency_id, self.invoice_id.company_id, rate_date)
            return round(amount_in_inr, 2)
        return round(amount, 2)

    def get_gst_rate(self, taxes_rate, line_id):
        taxes = ('SGST', 'CGST', 'IGST')
        gst_rate = float()
        for tax in taxes:
            gst_rate = gst_rate + taxes_rate.get(line_id, {}).get(tax, 0.0)
        return gst_rate

    @api.depends('invoice_id')
    def _compute_generate_request_json(self):
        for transaction in self.filtered(lambda t: t.invoice_id.state not in ('draft', 'cancel')):
            values = {
                'fields': fields,
                'invoice': transaction
            }
            generate_request_json = self.env['ir.ui.view'].render_template("l10n_in_einvoice.l10n_in_invoice_request_payload_json", values)
            generate_request_json = generate_request_json.decode("utf-8")
            json_dumps = json.dumps(safe_eval(generate_request_json))
            transaction.generate_request_json = json_dumps

    @api.depends('irn','cancel_reason','cancel_remarks')
    def _compute_cancel_request_json(self):
        for transaction in self.filtered(lambda t: t.invoice_id.state == 'cancel'):
            transaction.cancel_request_json = json.dumps({
                "Irn": transaction.irn,
                "CnlRsn": transaction.cancel_reason,
                "CnlRem": transaction.cancel_remarks,
            })

    @api.model
    def fix_base64(self, base64_string):
        # add missed = padding
        missing_padding = len(base64_string) % 4
        if missing_padding:
            base64_string += '=' * (4 - missing_padding)
        return base64_string

    def _process(self):
        self.ensure_one()
        service = self.env['l10n.in.einvoice.service'].get_service(self.invoice_id.company_id.partner_id)
        response = service.generate(transaction_id=self)
        response_data = response.get('data')
        if response_data and response_data.get('Irn') and response_data.get('SignedQRCode'):
            vals = {
                'response_json': json.dumps(response_data),
                'status': 'submitted',
            }
            self.sudo().write(vals)

    def submit_invoice(self):
        for transaction in self:
            transaction._process()

    def _process_cancel(self):
        self.ensure_one()
        service = self.env['l10n.in.einvoice.service'].get_service(self.invoice_id.company_id.partner_id)
        response = service.cancel(transaction_id=self)
        vals = {
            'cancel_response_json': str(response)
        }
        response_data = response.get('data', False)
        if response_data and response_data.get('CancelDate', False):
            cancellation_datatime = fields.Datetime.from_string(response_data.get('CancelDate')) - timedelta(hours=5, minutes=30, seconds=00)
            vals.update({
                'cancellation_datatime': cancellation_datatime,
                'status': 'cancel'
            })
        self.sudo().write(vals)
        self.env.cr.commit()

    def cancel_invoice(self, cancel_reason, cancel_remarks):
        self.sudo().write({
            'cancel_reason': cancel_reason,
            'cancel_remarks': cancel_remarks
        })
        for transaction in self:
            transaction._process_cancel()

    def preview_qrcode(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'target': 'new',
            'url': "/report/barcode/?type=%s&value=%s&width=%s&height=%s" % ('QR', self.qr_code_data, 200, 200),
        }
