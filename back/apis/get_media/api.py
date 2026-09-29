from core.bases.apis import BaseApi, pln

class GetMedia(BaseApi):
    def main(self):
        self.show_me()
        return {"Hello": "World", "message" : "Hello World"}
