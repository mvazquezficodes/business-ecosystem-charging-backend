# Orde de creación de cosas:
#   Necesito crear un plugin y después crear el service specification

import json
from copy import deepcopy
from datetime import datetime
from importlib import reload

from django.core.exceptions import PermissionDenied
from django.test import TestCase
from parameterized import parameterized


class ServiceSpecificationManagerTest(TestCase):

    tags = ("service-specification-manager",)

    def setUp(self):
        service_specification_imp.settings.SERVICE = "http://host.docker.internal:8638"

    def _addIdHref(self, gson, returned):
        print(returned['id'])

        gson["id"] = returned['id']
        gson["href"] = returned['href']

