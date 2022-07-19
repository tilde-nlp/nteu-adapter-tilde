from elg import QuartService
from elg.quart_service import ProcessingError
from elg.model import TextsResponse, TextsResponseObject
import aiohttp
import traceback
import os
import asyncio
from loguru import logger

GATEWAY_ENDPOINT = os.environ.get("GATEWAY_ENDPOINT", "http://localhost:10000/api/1.0.0/translate")
GATEWAY_READY = os.environ.get("GATEWAY_READY", "http://localhost:10000/")
SEGMENTER_READY = os.environ.get("SEGMENTER_READY", "http://localhost:6000/segment")
BACKEND_READY = os.environ.get("BACKEND_READY", "http://localhost:5000/translate/batch")

class NTEUAdapterTilde(QuartService):

    async def wait_for_success(self, component, make_request, expected_response_code = 200):
        logger.info(f"Waiting for {component} to become ready")
        tries = 30
        while tries > 0:
            tries -= 1
            try:
                async with make_request(self.session) as client_response:
                    resp_text = await client_response.text()
                    resp_len = len(resp_text)
                    logger.info(f"Request to {component} received response code {client_response.status}: {resp_len} characters in response")
                    if resp_len < 100:
                        logger.info(f"Response was: {resp_text}")
                    if client_response.status == expected_response_code:
                        logger.info(f"{component} is now 'successful'")
                        return
            except Exception as ex:
                logger.info(f"Request to {component} failed with an exception: {ex}")
            await asyncio.sleep(1)
        raise RuntimeError(f"{component} did not become ready")


    async def setup(self):
        self.session = aiohttp.ClientSession()
        # Ensure all dependencies are up before we start listening
        try:
            # First wait for the backend to be up and listening for requests at
            # all - we check this by sending the wrong HTTP method to the
            # endpoint and expecting a 405 method not allowed rather than a TCP
            # connection failure
            await self.wait_for_success("backend-up", lambda s: s.get(BACKEND_READY), 405)
            # Give backend a few seconds to complete initialization
            await asyncio.sleep(5)
            await asyncio.gather(
                self.wait_for_success("backend-working", lambda s: s.post(BACKEND_READY, json={'texts':['test']})),
                self.wait_for_success("gateway", lambda s: s.get(GATEWAY_READY)),
                self.wait_for_success("segmenter", lambda s: s.post(SEGMENTER_READY, json={'texts':['test'],'lang':'en'})),
            )
        except:
            os._exit(1)

    async def shutdown(self):
        if self.session is not None:
            await self.session.close()

    async def process_text(self, request):
        reply_texts = await self.call_gateway([request.content])
        return TextsResponse(texts=[TextsResponseObject(content=t, role="segment") for t in reply_texts])

    async def call_gateway(self, texts):
        # At most one of these two will be set inside the try
        err = None
        content = None
        try:
            remaining_tries = 4
            while remaining_tries > 0:
                # Make the remote call
                async with self.session.post(GATEWAY_ENDPOINT, json={'texts':texts}) as client_response:
                    status_code = client_response.status
                    if status_code >= 400:
                        err_text = await client_response.text()
                        if "Schema missing" in err_text:
                            # This is a known transient error with the backend, pause for a second and try again
                            logger.warning(f"Got transient error from backend, {remaining_tries} attempts remaining")
                            await asyncio.sleep(1)
                            remaining_tries -= 1
                        else:
                            err = ProcessingError.InternalError(err_text)
                            remaining_tries = 0
                    else:
                        content = await client_response.json()
                        remaining_tries = 0
        except:
            traceback.print_exc()
            raise ProcessingError.InternalError('Error calling API')

        if err:
            raise err
        elif content:
            return [t['translation'] for t in content['translations']]
        else:
            # Ran out of retries
            raise ProcessingError.InternalError("no response from backend")


service = NTEUAdapterTilde("NTEUAdapter")
app = service.app
