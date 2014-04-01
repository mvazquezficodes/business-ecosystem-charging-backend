# -*- coding: utf-8 -*-

# Copyright (c) 2013 CoNWeT Lab., Universidad Politécnica de Madrid

# This file is part of WStore.

# WStore is free software: you can redistribute it and/or modify
# it under the terms of the European Union Public Licence (EUPL)
# as published by the European Commission, either version 1.1
# of the License, or (at your option) any later version.

# WStore is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# European Union Public Licence for more details.

# You should have received a copy of the European Union Public Licence
# along with WStore.
# If not, see <https://joinup.ec.europa.eu/software/page/eupl/licence-eupl>.

import re
import json
from urllib2 import HTTPError

from django.contrib.auth.models import User
from django.http import HttpResponse
from django.views.decorators.http import require_http_methods
from django.conf import settings

from wstore.store_commons.utils.http import build_response, supported_request_mime_types, \
authentication_required
from wstore.store_commons.resource import Resource
from wstore.models import Organization, RSS
from django.contrib.auth.decorators import login_required
from wstore.admin.views import is_hidden_credit_card, is_valid_credit_card
from wstore.admin.rss.views import _check_limits
from wstore.rss_adaptor.expenditure_manager import ExpenditureManager


def get_organization_info(org):
    """
    Get the information of a concrete organization
    """
    if not org.private:
        org_element = {
            'name': org.name,
            'notification_url': org.notification_url,
        }
        if len(org.tax_address):
            org_element['tax_address'] = org.tax_address

        if 'number' in org.payment_info:
            number = org.payment_info['number']
            number = 'xxxxxxxxxxxx' + number[-4:]
            org_element['payment_info'] = {
                'number': number,
                'type': org.payment_info['type'],
                'expire_year': org.payment_info['expire_year'],
                'expire_month': org.payment_info['expire_month'],
                'cvv2': org.payment_info['cvv2'],
            }
        org_element['limits'] = org.expenditure_limits
    else:
        raise Exception('Private organization')

    return org_element


class OrganizationCollection(Resource):

    @authentication_required
    @supported_request_mime_types(('application/json',))
    def create(self, request):

        if not request.user.is_staff:
            return build_response(request, 403, 'Forbidden')

        try:
            data = json.loads(request.raw_post_data)

            tax_address = {}
            if 'tax_address' in data:
                tax_address = {
                    'street': data['tax_address']['street'],
                    'postal': data['tax_address']['postal'],
                    'city': data['tax_address']['city'],
                    'country': data['tax_address']['country']
                }

            payment_info = {}
            if 'payment_info' in data:
                if not is_valid_credit_card(data['payment_info']['number']):
                    raise Exception()

                payment_info = {
                    'type': data['payment_info']['type'],
                    'number': data['payment_info']['number'],
                    'expire_month': data['payment_info']['expire_month'],
                    'expire_year': data['payment_info']['expire_year'],
                    'cvv2': data['payment_info']['cvv2']
                }
            Organization.objects.create(
                name=data['name'],
                notification_url=data['notification_url'],
                tax_address=tax_address,
                payment_info=payment_info,
        private=False
            )
        except:
            return build_response(request, 400, 'Inavlid content')

        return build_response(request, 201, 'Created')

    @authentication_required
    def read(self, request):

        response = []

        # Get organization info
        for org in Organization.objects.all():
            try:
                org_element = get_organization_info(org)
            except:
                continue

            # Check if payment information is displayed
            if (not request.user.is_staff or request.user.pk in org.managers)\
            and 'payment_info' in org_element:
                del(org_element['payment_info'])

            response.append(org_element)

        return HttpResponse(json.dumps(response), status=200, mimetype='appliacation/json')


class OrganizationEntry(Resource):

    @authentication_required
    def read(self, request, org):

        try:
            org = Organization.objects.get(name=org)
            org_info = get_organization_info(org)
        except:
            return build_response(request, 404, 'Not found')

        # Check if the user can know the org payment info
        if (not request.user.is_staff or not request.user.pk in org.managers)\
        and 'payment_info' in org_info:
            del(org_info['payment_info'])

        return HttpResponse(json.dumps(org_info), status=200, mimetype='appliacation/json')

    @authentication_required
    @supported_request_mime_types(('application/json',))
    def update(self, request, org):

        # Get the organization
        try:
            organization = Organization.objects.get(name=org)
        except:
            return build_response(request, 404, 'Not found')

        if not request.user.is_staff and not request.user.pk in organization.managers:
            return build_response(request, 403, 'Forbidden')

        try:
            # Load request data
            data = json.loads(request.raw_post_data)
            if 'notification_url' in data:
                if data['notification_url'] and not re.match(re.compile(
                    r'^https?://'
                    r'(?:(?:[\w0-9](?:[\w0-9-]{0,61}[\w0-9])?\.)+[\w]{2,6}\.?|'
                    r'localhost|'
                    r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
                    r'(?::\d+)?'
                    r'(?:/?|[/?]\S+)$', re.IGNORECASE), data['notification_url']):
                    raise Exception('Invalid notification URL')

                organization.notification_url = data['notification_url']

            # Load the tax address
            new_taxaddr = {}
            if 'tax_address' in data and data['tax_address'] != {}:
                new_taxaddr = {
                    'street': data['tax_address']['street'],
                    'postal': data['tax_address']['postal'],
                    'city': data['tax_address']['city'],
                    'country': data['tax_address']['country']
                }

            organization.tax_address = new_taxaddr

            # Load the payment info
            new_payment = {}
            if 'payment_info' in data and data['payment_info'] != {}:

                number = data['payment_info']['number']

                if not is_valid_credit_card(number):
                    if 'number' in organization.payment_info and \
                    is_hidden_credit_card(number, organization.payment_info['number']):
                        number = organization.payment_info['number']
                    else:
                        raise Exception('Invalid credit card number')

                new_payment = {
                    'type': data['payment_info']['type'],
                    'number': number,
                    'expire_year': data['payment_info']['expire_year'],
                    'expire_month': data['payment_info']['expire_month'],
                    'cvv2': data['payment_info']['cvv2']
                }

            if 'limits' in data:
                limits = _check_limits(data['limits'])
                currency = limits['currency']
                # Get default RSS
                rss = RSS.objects.all()[0]
                exp_manager = ExpenditureManager(rss, rss.access_token)

                try:
                    exp_manager.set_actor_limit(limits, organization)
                except HTTPError as e:
                    if e.code == 401:
                        rss.refresh_token()
                        exp_manager.set_credentials(rss.access_token)
                        exp_manager.set_actor_limit(limits, organization)
                    else:
                        raise e

                # Save limits
                limits['currency'] = currency
                organization.expenditure_limits = limits

            organization.payment_info = new_payment
            organization.save()
        except Exception as e:
            msg = 'Invalid content'
            if e.message:
                msg = e.message
            return build_response(request, 400, msg)

        return build_response(request, 200, 'OK')


@login_required
@require_http_methods(['PUT'])
def change_current_organization(request):

    # Get the requested organization
    data = json.loads(request.raw_post_data)
    try:
        org = Organization.objects.get(name=data['organization'])
    except:
        return build_response(request, 404, 'Not found')

    # Check that the user belongs to the organization
    found = False
    for o in request.user.userprofile.organizations:
        if o['organization'] == org.pk:
            found = True
            break

    if not found:
        return build_response(request, 403, 'Forbidden')

    # Change the current organization
    request.user.userprofile.current_organization = org
    request.user.userprofile.save()

    return build_response(request, 200, 'OK')


class OrganizationUserCollection(Resource):

    @authentication_required
    @supported_request_mime_types(('application/json',))
    def create(self, request, org):

        if settings.OILAUTH:
            return build_response(request, 403, 'It is not possible to modify organizations (use Account enabler instead)')

        try:
            organization = Organization.objects.get(name=org)
        except:
            return build_response(request, 404, 'Organization not found')

        # Check if the organization is private
        if organization.private:
            return build_response(request, 403, 'Forbidden')

        # Check if the user can include users in the organization
        if not request.user.is_staff and not request.user.pk in organization.managers:
            return build_response(request, 403, 'Forbidden')

        # Get the user
        try:
            data = json.loads(request.raw_post_data)
            user = User.objects.get(username=data['user'])

            if not 'roles' in data:
                raise Exception('')
        except:
            return build_response(request, 400, 'Invalid JSON content')

        org_roles = []
        if 'provider' in data['roles']:
            org_roles.append('provider')

        if 'customer' in data['roles']:
            org_roles.append('customer')

        # Check if the user already belongs to the organization
        belongs = False
        for o in user.userprofile.organizations:
            if o['organization'] == organization.pk:
                belongs = True

        if belongs == True:
            return build_response(request, 400, 'The user already belongs to the organization')

        # Include the new user
        user.userprofile.organizations.append({
            'organization': organization.pk,
            'roles': org_roles
        })
        user.userprofile.save()

        # Check if the user is a new manager
        if 'manager' in data['roles']:
            organization.managers.append(user.pk)
            organization.save()

        return build_response(request, 200, 'OK')
