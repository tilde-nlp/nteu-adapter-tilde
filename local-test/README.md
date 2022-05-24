# Testing the adapter locally

To run a local test of the adapter, you must create a file named `.env` with the line

```
TRANSLATOR_IMAGE={image-reference}
```

giving the image reference for the NTEU translation service that the adapter will be calling.  Then you should be able to run `docker-compose up` and point your browser at http://localhost:8080 to test the service via its GUI.  The compose file assumes that the adapter is built and tagged as `nteu-adapter-tilde:latest`.
