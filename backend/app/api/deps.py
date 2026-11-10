from fastapi import Request

from ..services.pipeline import Services


def get_services(request: Request) -> Services:
    return request.app.state.services
