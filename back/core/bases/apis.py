# Python
import os
import json
from inspect import currentframe

# FastApi
from fastapi import status
from fastapi import HTTPException
from fastapi import WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

# Ojitos369
from ojitos369.errors import CatchErrors as CE
from ojitos369.utils import get_d, print_line_center, printwln as pln
from core.websockets.manager import ConnectionManager
from .utils import ClassBase

from core.conf.settings import MYE, ce, prod_mode, dev_mode

sec_code = "0e5a332d-9e2e-427d-bd84-4e581fe8a806"


class BaseApi(ClassBase):
    def __init__(self, *args, **kwargs):
        self.request = kwargs.get('request', None)
        self.data = {}
        for key, value in kwargs.items():
            if key != "request":
                self.data[key] = value
        if args:
            self.data['args'] = args

        self.status = 200
        self.response = {}
        self.ce = ce
        self.MYE = MYE
        self.response_mode = 'json'
        self.extra_error = ""

    def errors(self, e):
        try:
            self.extra_error = f'\n{self.extra_error}'
            self.extra_error += f'\nIp de la petition: {self.petition_ip}'
            raise e
        except MYE as e:
            error = self.ce.show_error(e, extra=self.extra_error)
            print_line_center(error)
            raise HTTPException(
                status_code = status.HTTP_400_BAD_REQUEST,
                detail = str(e)
            )
        except Exception as e:
            error = self.ce.show_error(e, send_email=False, extra=self.extra_error)
            print_line_center(error)
            raise HTTPException(
                status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail = str(e)
            )

    async def get_post_data(self):
        try:
            data = await self.request.json()
        except Exception as e:
            data = {}
        for key, value in data.items():
            self.data[key] = value
    
    def get_get_data(self):
        data = self.request.query_params
        for key, value in data.items():
            self.data[key] = value
    
    def validate_session(self):
        cookies = self.request.cookies
        mi_cookie = cookies.get('reapi', '')
        auth_code = self.request.headers.get("authorization", None)
        self.token = mi_cookie or auth_code
        # print(f"Authorization header: {auth_code}")
        # pln(mi_cookie)
        if not self.token:
            raise self.MYE("Sesion no valida")

    def validar_permiso(self, usuarios_validos):
        pass

    def show_me(self):
        class_name = self.__class__.__name__
        cf = currentframe()
        line = cf.f_back.f_lineno
        file_name = cf.f_back.f_code.co_filename
        print_line_center(f"{class_name} - {file_name}:{line} ")

    def get_client_ip(self):
        ip = ''
        try:
            ip = self.request.client.host
        except:
            ip = 'unknown'
        self.petition_ip = ip

    async def run(self):
        self.get_client_ip()
        try:
            self.get_get_data()
            await self.get_post_data()
        except Exception as e:
            self.errors(e)
        try:
            await run_in_threadpool(self.validate_session)
            result = await run_in_threadpool(self.main)
            return result or self.response
        except Exception as e:
            self.errors(e)
        finally:
            pass


class AsyncApi(BaseApi):
    """Like BaseApi but `main` (and `validate_session`) are coroutines, for work that awaits (jobs runner, uploads)."""
    async def run(self):
        self.get_client_ip()
        try:
            self.get_get_data()
            await self.get_post_data()
        except Exception as e:
            self.errors(e)
        try:
            await self.validate_session()
            result = await self.main()
            return result if result is not None else self.response
        except HTTPException:
            raise
        except Exception as e:
            self.errors(e)

    async def validate_session(self):
        pass   # local single-user app (server binds to 127.0.0.1)


class PostApi(BaseApi):
    def post(self, request, **kwargs):
        return self.exec(request, **kwargs)


class GetApi(BaseApi):
    def get(self, request, **kwargs):
        return self.exec(request, **kwargs)


class PutApi(BaseApi):
    def put(self, request, **kwargs):
        return self.exec(request, **kwargs)


class DeleteApi(BaseApi):
    def delete(self, request, **kwargs):
        return self.exec(request, **kwargs)


class PatchApi(BaseApi):
    def patch(self, request, **kwargs):
        return self.exec(request, **kwargs)


class FullApi(BaseApi):
    def gen(self, request, **kwargs):
        return self.exec(request, **kwargs)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.post = self.get = self.put = self.patch = self.delete = self.gen


class WebSocketApi:
    def __init__(self, websocket: WebSocket, manager: ConnectionManager, **kwargs):
        self.websocket = websocket
        self.manager = manager
        self.data = kwargs
        self.validate_session()
    
    def validate_session(self):
        auth_code = self.websocket.query_params.get("clientId", None)
        if not auth_code:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized access"
            )
        # LAN access: devices other than this machine need the access token cookie (see main.lan_guard)
        host = self.websocket.client.host if self.websocket.client else ""
        if host not in ("127.0.0.1", "::1", "localhost"):
            import secrets
            from core.conf.workspace import local_settings
            if not secrets.compare_digest(self.websocket.cookies.get("vs_token", ""), local_settings.load()["access"]["token"]):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized access")

    async def on_connect(self):
        pass

    async def on_receive(self, data: any):
        pass

    async def on_disconnect(self):
        pass

    async def handle_connection(self):
        chat_id = self.data.get('chat_id', 'default')

        await self.manager.connect(self.websocket, chat_id)
        await self.on_connect()
        try:
            while True:
                data = await self.websocket.receive_text()
                await self.on_receive(data)
        except WebSocketDisconnect:
            pass
        finally:
            self.manager.disconnect(self.websocket, chat_id)
            await self.on_disconnect()



