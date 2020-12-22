# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import RedirectWarning

from odoo.addons.iap import jsonrpc

DEFAULT_ENDPOINT = "https://einvoice.odoo.co.in"


class InvoiceService(models.Model):
    _name = "l10n.in.einvoice.service"
    _description = "eInvoice Client"

    partner_id = fields.Many2one("res.partner", string="GSTN Partner")
    gstin = fields.Char("GSTIN")
    gstn_username = fields.Char("Username")
    gstn_password = fields.Char("Password")
    token = fields.Char("Token")
    token_validity = fields.Datetime("Valid Until")
    is_token_valid = fields.Boolean(compute="_is_token_valid", string="Valid Token")

    def _is_token_valid(self):
        for service in self:
            if service.token_validity and service.token_validity > fields.Datetime.now():
                service.is_token_valid = True
            else:
                service.is_token_valid = False

    @api.model
    def get_service(self, partner):
        service = self.search(
            [("partner_id", "=", partner.id), ("gstin", "=", partner.vat)], limit=1
        )
        if not service:
            action = self.env.ref(
                "l10n_in_einvoice.l10n_in_einvoice_generate_token_wizard_action"
            )
            raise RedirectWarning(
                "Please configure GSTN IAP Service for %s with GSTIN: %s"
                % (partner.name, partner.vat),
                action.id,
                _("Configure"),
            )
        return service

    def _connect_to_server(self, url_path, params):
        self.ensure_one()
        user_token = self.env["iap.account"].get("einvoice_india")
        params.update(
            {
                "account_token": user_token.account_token,
                "username": self.gstn_username,
                "gstin": self.gstin,
            }
        )
        endpoint = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("einvoice_india.endpoint", DEFAULT_ENDPOINT)
        )
        url = "%s%s" % (endpoint, url_path)
        return jsonrpc(url, params=params)

    def get_token(self):
        self.ensure_one()
        if self.is_token_valid:
            return self.token
        elif self.gstn_password:
            self.authenticate()
            return self.token
        else:
            action = self.env.ref(
                "l10n_in_einvoice.l10n_in_einvoice_generate_token_wizard_action"
            )
            raise RedirectWarning(
                "Please generate token for %s" % (self.partner_id.name),
                action.id,
                _("Generate"),
            )

    def setup(self, gstn_password=None):
        self.ensure_one()
        password = gstn_password or self.gstn_password
        params = {"password": password}
        response = self._connect_to_server(
            url_path="/iap/einvoice/setup", params=params
        )
        self.token_validity = fields.Datetime.from_string(
            response["data"]["TokenExpiry"]
        ) - timedelta(hours=5, minutes=30, seconds=00)
        self.token = response["data"]["AuthToken"]

    def authenticate(self, gstn_password=None):
        self.ensure_one()
        # If password is saved then no need to pass password else required
        password = gstn_password or self.gstn_password
        params = {"password": password}
        response = self._connect_to_server(
            url_path="/iap/einvoice/authenticate", params=params
        )
        # validity data-time in Indian standard time(UTC+05:30) so remove that gap and store in odoo
        self.token_validity = fields.Datetime.from_string(
            response["data"]["TokenExpiry"]
        ) - timedelta(hours=5, minutes=30, seconds=00)
        self.token = response["data"]["AuthToken"]

    def generate(self, transaction_id):
        self.ensure_one()
        token = self.get_token()
        params = {
            "auth_token": token,
            "json_payload": json.loads(transaction_id.generate_request_json),
        }
        return self._connect_to_server(
            url_path="/iap/einvoice/type/GENERATE/version/V1_03", params=params
        )

    def cancel(self, transaction_id):
        self.ensure_one()
        token = self.get_token()
        params = {
            "auth_token": token,
            "json_payload": json.loads(transaction_id.cancel_request_json),
        }
        return self._connect_to_server(
            url_path="/iap/einvoice/type/CANCEL/version/V1_03", params=params
        )
