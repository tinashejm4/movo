from decimal import Decimal
from pathlib import Path
import json

from django.shortcuts import get_object_or_404
from apps.users.permissions import IsStaff
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import OpenApiResponse, extend_schema

from apps.users.models import City, Suburb, SuburbAlias

class CityView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    def get(self, request):
        cities = City.objects.all()
        data = [
            {
                "id": city.id,
                "name": city.name,
            }
            for city in cities
        ]
        return Response(data, status=status.HTTP_200_OK)


class SuburbView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    def get(self, request, city_id):
        city = get_object_or_404(City, id=city_id)
        suburbs = Suburb.objects.filter(city=city)
        aliases = SuburbAlias.objects.filter(suburb__in=suburbs)
        data = [
            {
                "id": suburb.id,
                "name": suburb.name,
                "is_active": suburb.is_active,
                "x_coord": suburb.x_coord,
                "y_coord": suburb.y_coord,
                "aliases": [alias.alias for alias in aliases if alias.suburb_id == suburb.id] if aliases else None,
            }
            for suburb in suburbs
        ]
        return Response(data, status=status.HTTP_200_OK)

    def post(self, request, city_id):
        city = get_object_or_404(City, id=city_id)
        suburb_id = request.data.get("suburb_id")
        suburb = get_object_or_404(Suburb, id=suburb_id, city=city)

        suburb.name = request.data.get("name", suburb.name)
        suburb.is_active = request.data.get("is_active", suburb.is_active)
        suburb.x_coord = request.data.get("x_coord", suburb.x_coord)
        suburb.y_coord = request.data.get("y_coord", suburb.y_coord)
        suburb.save()

        return Response(
            {
                "id": suburb.id,
                "name": suburb.name,
                "is_active": suburb.is_active,
                "x_coord": suburb.x_coord,
                "y_coord": suburb.y_coord,
            },
            status=status.HTTP_200_OK,
        )

class SuburbsImportView(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    @extend_schema(
        tags=["Users"],
        responses={
            200: OpenApiResponse(description="Areas imported successfully"),
            400: OpenApiResponse(description="Invalid data in areas.json"),
            404: OpenApiResponse(description="suburbs data or CBD area not found"),
        },
    )
    def post(self, request):

        surburbs_data  = request.data.get("suburbs", [])
        city_id = request.data.get("city_id")

        areas = surburbs_data
        if not isinstance(areas, list):
            return Response(
                {"error": "suburbs data must be a JSON array"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        created_count = 0
        updated_count = 0
        skipped_count = 0

        for row in areas:
            city = get_object_or_404(City, id=city_id)
            area_name = str(row.get("Areas", "")).strip()
            if not area_name:
                skipped_count += 1
                continue

            try:
                lat = float(row["x"])
                lon = float(row["y"])
            except (TypeError, ValueError, KeyError):
                skipped_count += 1
                continue

            defaults = {
                "x_coord": Decimal(str(lat)),
                "y_coord": Decimal(str(lon)),
            }
            _, created = Suburb.objects.update_or_create(
                city=city,
                name=area_name,
                defaults=defaults,
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        return Response(
            {
                "message": "Areas imported successfully",
                "city": city.name,
                "created": created_count,
                "updated": updated_count,
                "skipped": skipped_count,
                "total": len(areas),
            },
            status=status.HTTP_200_OK,
        )

class SuburbAliasiew(APIView):
    permission_classes = [IsAuthenticated, IsStaff]

    @extend_schema(
        tags=["Users"],
        responses={
            200: OpenApiResponse(description="Suburb alias added successfully"),
            400: OpenApiResponse(description="Invalid data"),
            404: OpenApiResponse(description="Suburb or alias not found"),
        },
    )
    def post(self, request):
        suburb_id = request.data.get("suburb_id")
        alias_name = request.data.get("alias_name")

        suburb = get_object_or_404(Suburb, id=suburb_id)
        _, created = SuburbAlias.objects.update_or_create(
            suburb=suburb,
            alias=alias_name,
        )

        return Response(
            {
                "message": "Suburb alias added successfully",
                "suburb": suburb.name,
                "alias": alias_name,
            },
            status=status.HTTP_200_OK,
        )


    def get(self, request):
        suburb_aliases = SuburbAlias.objects.all()
        data = [
            {
                "suburb": alias.suburb.name,
                "alias": alias.alias,
            }
            for alias in suburb_aliases
        ]
        return Response(
            {
                "message": "Suburb aliases retrieved successfully",
                "data": data,
            },
            status=status.HTTP_200_OK,
        )
