from elg import QuartService
from elg.quart_service import ProcessingError
from elg.model import TextsResponse, TextsResponseObject
import aiohttp
import traceback
import os
import asyncio
from loguru import logger
import websockets

GATEWAY_ENDPOINT = os.environ.get("GATEWAY_ENDPOINT", "http://localhost:10000/api/1.0.0/translate")
GATEWAY_READY = os.environ.get("GATEWAY_READY", "http://localhost:10000/")
SEGMENTER_READY = os.environ.get("SEGMENTER_READY", "http://localhost:6000/segment")
BACKEND_READY = os.environ.get("BACKEND_READY", "http://localhost:5000/translate/batch")
MARIAN_READY = os.environ.get("MARIAN_READY", "ws://localhost:8050/translate")

class NTEUAdapterTilde(QuartService):

    async def wait_for_success(self, component, make_request):
        logger.info(f"Waiting for {component} to become ready")
        tries = 30
        while tries > 0:
            tries -= 1
            try:
                async with make_request(self.session) as client_response:
                    resp_text = await client_response.text()
                    resp_len = len(resp_text)
                    if client_response.ok:
                        logger.info(f"Request to {component} succeeded: {resp_len} characters in response")
                        if resp_len < 100:
                            logger.info(f"Response was: {resp_text}")
                        return
                    else:
                        logger.info(f"Request to {component} failed: {resp_len} characters in response")
            except Exception as ex:
                logger.info(f"Request to {component} failed with an exception: {ex}")
            await asyncio.sleep(1)
        raise RuntimeError(f"{component} did not become ready")

    async def wait_for_marian(self):
        logger.info("Waiting for marian-server to become ready")
        tries = 30
        while tries > 0:
            tries -= 1
            try:
                async with websockets.connect(MARIAN_READY) as websocket:
                    await websocket.send("Test")
                    resp_text = await websocket.recv()
                    resp_len = len(resp_text)
                    logger.info(f"Marian responded with {resp_len} characters")
                    if resp_len < 100:
                        logger.info(f"Response was: {resp_text}")
                    return
            except Exception as ex:
                logger.info(f"Request to marian failed with an exception: {ex}")
            await asyncio.sleep(1)
        raise RuntimeError(f"marian did not become ready")


    async def setup(self):
        self.session = aiohttp.ClientSession()
        # Ensure all dependencies are up before we start listening
        try:
            await asyncio.gather(
                self.wait_for_success("gateway", lambda s: s.get(GATEWAY_READY)),
                self.wait_for_success("segmenter", lambda s: s.post(SEGMENTER_READY, json={'texts':['test'],'lang':'en'})),
                self.wait_for_marian()
            )
            await asyncio.sleep(3)
            await self.wait_for_success("backend", lambda s: s.post(BACKEND_READY, json={'texts':['test']}))
        except:
            os._exit(1)

    async def shutdown(self):
        if self.session is not None:
            await self.session.close()

    async def process_text(self, request):
        reply_texts = await self.call_gateway([request.content])
        return TextsResponse(texts=[TextsResponseObject(content=t, role="segment") for t in reply_texts])

    async def call_gateway(self, texts):
        try:
            # Make the remote call
            async with self.session.post(GATEWAY_ENDPOINT, json={'texts':texts}) as client_response:
                status_code = client_response.status
                if status_code >= 400:
                    raise ProcessingError.InternalError(await client_response.text())
                content = await client_response.json()
                return [t['translation'] for t in content['translations']]
        except:
            traceback.print_exc()
            raise ProcessingError.InternalError('Error calling API')


service = NTEUAdapterTilde("NTEUAdapter")
app = service.app
