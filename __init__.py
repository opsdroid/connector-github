import json
import logging

import aiohttp

from opsdroid.connector import Connector
from opsdroid.message import Message

import requests


_LOGGER = logging.getLogger(__name__)
GITHUB_API_URL = "https://api.github.com"


class ConnectorGitHub(Connector):

    def __init__(self, config):
        """Setup the connector."""
        logging.debug("Loaded GitHub connector")
        super().__init__(config)
        self.config = config
        try:
            self.github_token = config["github-token"]
        except KeyError as e:
            _LOGGER.error("Missing auth token! You must set 'github-token' in your config")

        # remembering the bot's github username for future reference.
        res = requests.get("https://api.github.com/user?access_token="+self.github_token)
        responseData = json.parse(res.text)
        self.githubUsername = responseData["login"]
        self.name = self.config.get("name", "github")
        self.opsdroid = None

    async def connect(self, opsdroid):
        """Connect to GitHub."""
        self.opsdroid = opsdroid

        self.opsdroid.web_server.web_app.router.add_post(
            "/connector/{}".format(self.name),
            self.github_message_handler)

    async def listen(self, opsdroid):
        """Listen for new message."""
        pass  # Listening is handled by the aiohttp web server

    async def github_message_handler(self, request):
        """Handle event from GitHub."""
        req = await request.post()
        payload = json.loads(req["payload"])
        try:
            if payload["action"] == "created" and "comment" in payload:
                issue_number = payload["issue"]["number"]
                body = payload["comment"]["body"]
            elif payload["action"] == "opened" and "issue" in payload:
                issue_number = payload["issue"]["number"]
                body = payload["issue"]["body"]
            elif payload["action"] == "opened" and "pull_request" in payload:
                issue_number = payload["pull_request"]["number"]
                body = payload["pull_request"]["body"]
            else:
                _LOGGER.debug("No message to respond to.")
                _LOGGER.debug(payload)
                return aiohttp.web.Response(
                        text=json.dumps("No message to respond to."), status=200)

            issue = "{}/{}#{}".format(payload["repository"]["owner"]["login"],
                                      payload["repository"]["name"],
                                      issue_number)
            message = Message(body,
                              payload["sender"]["login"],
                              issue,
                              self)
            await self.opsdroid.parse(message)
        except KeyError as error:
            _LOGGER.error(error)

        return aiohttp.web.Response(
                text=json.dumps("Received"), status=201)

    async def respond(self, message):
        """Respond with a message."""
        # stop immediately if the message is from the bot itself.
        if message.user == self.githubUsername:
            return
        _LOGGER.debug("Responding via GitHub")
        repo, issue = message.room.split('#')
        url = "{}/repos/{}/issues/{}/comments".format(GITHUB_API_URL, repo, issue)
        headers = {'Authorization': ' token {}'.format(self.github_token)}
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={"body": message.text}, headers=headers) as resp:
                if resp.status == 201:
                    _LOGGER.error("Message sent.")
                    return True
                else:
                    _LOGGER.error(await resp.json())
                    return False
