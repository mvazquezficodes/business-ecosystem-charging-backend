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

from django.http import Http404, HttpResponseForbidden, HttpResponseNotAllowed

from wstore.store_commons.authentication import Http403

METHOD_MAPPING = {
    "GET": "read",
    "POST": "create",
    "PUT": "update",
    "DELETE": "delete",
    "PATCH": "patch",
}


class Resource(object):
    def __init__(self, authentication=None, permitted_methods=None):
        self.permitted_methods = tuple([m.upper() for m in permitted_methods])

        for method in self.permitted_methods:
            if method not in METHOD_MAPPING or not callable(getattr(self, METHOD_MAPPING[method], None)):
                raise Exception("Missing method: " + method)

    def __call__(self, request, *args, **kwargs):
        request_method = request.method.upper()
        if request_method not in self.permitted_methods:
            return HttpResponseNotAllowed(self.permitted_methods)

        try:
            return getattr(self, METHOD_MAPPING[request_method])(request, *args, **kwargs)
        except Http404:
            raise
        except Http403:
            return HttpResponseForbidden()
