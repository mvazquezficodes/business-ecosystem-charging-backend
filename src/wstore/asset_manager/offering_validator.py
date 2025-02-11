# -*- coding: utf-8 -*-

# Copyright (c) 2016 CoNWeT Lab., Universidad Politécnica de Madrid
# Copyright (c) 2020 Future Internet Consulting and Development Solutions S.L.

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

from decimal import Decimal

import requests

from wstore.asset_manager.catalog_validator import CatalogValidator
from wstore.asset_manager.models import Resource
from wstore.asset_manager.resource_plugins.decorators import on_product_offering_validation
from wstore.ordering.models import Offering
from wstore.store_commons.utils.units import ChargePeriod, CurrencyCode


class OfferingValidator(CatalogValidator):
    def _get_bundled_offerings(self, product_offering):
        bundled_offerings = []

        # Validate Bundle fields
        if "isBundle" in product_offering and product_offering["isBundle"]:
            if "bundledProductOffering" not in product_offering:
                raise ValueError("Offering bundles must contain a bundledProductOffering field")

            if len(product_offering["bundledProductOffering"]) < 2:
                raise ValueError("Offering bundles must contain at least two bundled offerings")

            for bundle in product_offering["bundledProductOffering"]:
                # Check if the specified offerings have been already registered
                offerings = Offering.objects.filter(off_id=bundle["id"])
                if not len(offerings):
                    raise ValueError("The bundled offering " + bundle["id"] + " is not registered")

                bundled_offerings.append(offerings[0])

        return bundled_offerings

    def _count_resource_offerings(self, asset):
        count = 0
        if asset is not None:
            offerings = Offering.objects.filter(asset=asset)
            count = len(offerings)
        return count

    def _set_asset_public_status(self, asset, is_open):
        if is_open and len(asset.bundled_assets) > 0:
            # If the asset is single set the is_public flag
            raise ValueError("Product bundles cannot be published in open offerings. Create an offering bundle instead")

        asset.is_public = is_open
        asset.save()

    @on_product_offering_validation
    def _validate_offering_pricing(self, provider, product_offering, bundled_offerings):
        is_open = False

        # Validate offering pricing fields
        if "productOfferingPrice" in product_offering:
            names = []
            for price_model in product_offering["productOfferingPrice"]:
                if "name" not in price_model:
                    raise ValueError("Missing required field name in productOfferingPrice")

                if price_model["name"].lower() in names:
                    raise ValueError("Price plans names must be unique (" + price_model["name"] + ")")

                names.append(price_model["name"].lower())

                # Check if the offering is an open offering
                if price_model["name"].lower() == "open" and (
                    len(price_model.keys()) == 1 or (len(price_model.keys()) == 2 and "description" in price_model)
                ):
                    is_open = True
                    continue

                # Validate price unit
                if "priceType" not in price_model:
                    raise ValueError("Missing required field priceType in productOfferingPrice")

                if (
                    price_model["priceType"] != "one time"
                    and price_model["priceType"] != "recurring"
                    and price_model["priceType"] != "usage"
                ):
                    raise ValueError("Invalid priceType, it must be one time, recurring, or usage")

                if price_model["priceType"] == "recurring" and "recurringChargePeriod" not in price_model:
                    raise ValueError("Missing required field recurringChargePeriod for recurring priceType")

                if price_model["priceType"] == "recurring" and not ChargePeriod.contains(
                    price_model["recurringChargePeriod"]
                ):
                    raise ValueError("Unrecognized recurringChargePeriod: " + price_model["recurringChargePeriod"])

                # Validate currency
                if "price" not in price_model:
                    raise ValueError("Missing required field price in productOfferingPrice")

                if "currencyCode" not in price_model["price"]:
                    raise ValueError("Missing required field currencyCode in price")

                if not CurrencyCode.contains(price_model["price"]["currencyCode"]):
                    raise ValueError("Unrecognized currency: " + price_model["price"]["currencyCode"])

                if Decimal(price_model["price"]["taxIncludedAmount"]) <= Decimal("0"):
                    raise ValueError("Invalid price, it must be greater than zero.")

            if is_open and len(names) > 1:
                raise ValueError("Open offerings cannot include price plans")

        return is_open

    def _download(self, url):
        r = requests.get(url)

        if r.status_code != 200:
            raise ValueError("There has been a problem accessing the product spec included in the offering")

        return r.json()

    def _get_offering_asset(self, product_offering, bundled_offerings):
        asset = None
        # Check if the offering is a bundle
        if not len(bundled_offerings):
            assets = Resource.objects.filter(product_id=product_offering["productSpecification"]["id"])

            if len(assets):
                asset = assets[0]

            is_digital = asset is not None
        else:
            # Check if the bundle is digital
            digital = len([offering for offering in bundled_offerings if offering.is_digital])

            if digital > 0 and digital != len(bundled_offerings):
                raise ValueError(
                    "Mixed bundle offerings are not allowed. All bundled offerings must be digital or physical"
                )

            is_digital = digital > 0

        return asset, is_digital

    def _validate_offering_model(self, product_offering, bundled_offerings, is_open):
        asset, is_digital = self._get_offering_asset(product_offering, bundled_offerings)

        # Open offerings only can be digital
        if is_open and not is_digital:
            raise ValueError("Non digital products cannot be open")

        # If the offering is a bundle and is open all the bundled offerings must be open
        if is_open and len(bundled_offerings) != len([offer for offer in bundled_offerings if offer.is_open]):
            raise ValueError("If a bundle is open all the bundled offerings must be open")

        return asset, is_digital

    def _build_offering_model(self, provider, product_offering, bundled_offerings, is_open):
        asset, is_digital = self._validate_offering_model(product_offering, bundled_offerings, is_open)

        # Open products can only be included in a single offering
        offering_count = self._count_resource_offerings(asset)
        if is_digital and (
            (is_open and offering_count > 0) or (not is_open and offering_count == 1 and asset.is_public)
        ):
            raise ValueError("Assets of open offerings cannot be monetized in other offerings")

        # Check if the offering contains a description
        description = ""
        if "description" in product_offering:
            description = product_offering["description"]

        if asset is not None:
            self._set_asset_public_status(asset, is_open)

        Offering.objects.create(
            owner_organization=provider,
            name=product_offering["name"],
            description=description,
            version=product_offering["version"],
            is_digital=is_digital,
            asset=asset,
            is_open=is_open,
            bundled_offerings=[offering.pk for offering in bundled_offerings],
        )

    def attach_info(self, provider, product_offering):
        # Find the offering model to attach the info
        offerings = Offering.objects.filter(
            off_id=None,
            owner_organization=provider,
            name=product_offering["name"],
            version=product_offering["version"],
        )

        if not len(offerings):
            raise ValueError("The specified offering has not been registered")

        offering = offerings[0]
        offering.off_id = product_offering["id"]
        offering.href = product_offering["href"]
        offering.save()

    def validate_creation(self, provider, product_offering):
        bundled_offerings = self._get_bundled_offerings(product_offering)
        is_open = self._validate_offering_pricing(provider, product_offering, bundled_offerings)
        self._build_offering_model(provider, product_offering, bundled_offerings, is_open)

    def validate_update(self, provider, product_offering):
        bundled_offerings = self._get_bundled_offerings(product_offering)
        is_open = self._validate_offering_pricing(provider, product_offering, bundled_offerings)

        asset, is_digital = self._validate_offering_model(product_offering, bundled_offerings, is_open)

        # Open products can only be included in a single offering
        if is_open and self._count_resource_offerings(asset) > 1:
            raise ValueError("Assets of open offerings cannot be monetized in other offerings")

        if asset is not None:
            self._set_asset_public_status(asset, is_open)
