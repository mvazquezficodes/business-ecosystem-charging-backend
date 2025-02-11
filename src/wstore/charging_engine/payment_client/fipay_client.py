# -*- coding: utf-8 -*-

# Copyright (c) 2013 - 2016 CoNWeT Lab., Universidad Politécnica de Madrid

# This file belongs to the business-charging-backend
# of the Business API Ecosystem.

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import json

import urllib2
from django.contrib.sites.models import Site
from urllib2 import HTTPError

from wstore.charging_engine.payment_client.payment_client import PaymentClient
from wstore.store_commons.utils.method_request import MethodRequest

FIPAY_ENDPOINT = "http://antares.ls.fi.upm.es:8002"


class FiPayClient(PaymentClient):
    _purchase = None
    _redirection = None

    def start_redirection_payment(self, price, currency):
        url = Site.objects.all()[0].domain
        if url[-1] != "/":
            url += "/"

        # Load request data
        request_data = {
            "offering": {
                "organization": self._purchase.offering.owner_organization.name,
                "name": self._purchase.offering.name,
                "version": self._purchase.offering.version,
            },
            "callback_url": url + "api/contracting/" + self._purchase.ref + "/accept",
            "error_url": url + "api/contracting/" + self._purchase.ref + "/cancel",
            "price": str(price),
        }
        # Build request
        token = self._purchase.customer.userprofile.access_token
        body = json.dumps(request_data)
        headers = {
            "Content-type": "application/json",
            "Authorization": "Bearer " + token,
        }

        request = MethodRequest("POST", FIPAY_ENDPOINT + "/api/payment", body, headers)

        opener = urllib2.build_opener()

        try:
            response = opener.open(request)
        except HTTPError as e:
            if e.code == 401:
                msg = "The connection with FiPay has returned an unauthorized code, this can happen if you have never accessed FiPay, so your user profile has not been created."
            else:
                msg = "The connection with FiPay has failed"
            raise Exception(msg)

        # Return redirection URL
        self._redirection = json.loads(response.read())["url"]

    def end_redirection_payment(self, token, payer_id):
        # Build request
        request_data = {"token": token}

        # Build request
        user_token = self._purchase.customer.userprofile.access_token
        body = json.dumps(request_data)
        headers = {
            "Content-type": "application/json",
            "Authorization": "Bearer " + user_token,
        }

        request = MethodRequest("POST", FIPAY_ENDPOINT + "/api/end", body, headers)

        opener = urllib2.build_opener()

        try:
            opener.open(request)
        except:
            raise Exception("The connection with FiPay has failed")

    def direct_payment(self, currency, price, credit_card):
        pass

    def get_checkout_url(self):
        return self._redirection
