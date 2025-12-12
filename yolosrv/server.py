import argparse
import asyncio
import json
import logging
import os
import cv2
import numpy as np
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack
from av import VideoFrame
from ultralytics import YOLO

# ログ設定
logging.basicConfig(level=logging.INFO)

# YOLOモデルのロード (初回実行時に自動でダウンロードされます)
model = YOLO("yolov5n.pt")

pcs = set()

class VideoTransformTrack(MediaStreamTrack):
    kind = "video"

    def __init__(self, track):
        super().__init__()
        self.track = track

    async def recv(self):
        # 1. スマホからフレームを受け取る
        frame = await self.track.recv()
        
        # 2. aiortcのフレームをnumpy配列(OpenCV形式)に変換
        img = frame.to_ndarray(format="bgr24")

        # 3. YOLOで物体認識を実行
        # stream=Trueにはせず、単発推論します
        # --- 修正点: ラズパイ/CPU環境向けに軽量化 ---
        # imgsz=320: デフォルト640の半分のサイズで推論。計算量が約1/4になり高速化します。
        # 精度が落ちすぎたと感じたら 416 や 480 に上げてください。
        results = model(img, imgsz=320, verbose=False)
        # -------------------------------------------
        
        # 4. 認識結果（バウンディングボックス）を画像に描画
        annotated_frame = results[0].plot()

        # --- 修正点: サーバー動作のため画面表示(imshow)を削除しました ---
        # cv2.imshow("Processed Stream", annotated_frame)
        # if cv2.waitKey(1) & 0xFF == ord('q'):
        #     asyncio.get_event_loop().stop()
        # -----------------------------------------------------------

        # 6. 加工した画像を新しいVideoFrameに変換してスマホへ返す
        # ここが重要: 元のframeのタイムスタンプを引き継がないと再生されません
        new_frame = VideoFrame.from_ndarray(annotated_frame, format="bgr24")
        new_frame.pts = frame.pts
        new_frame.time_base = frame.time_base
        
        return new_frame

async def index(request):
    # 同じディレクトリにあるindex.htmlを読み込む想定
    content = open(os.path.join(os.path.dirname(__file__), "index.html"), "r").read()
    return web.Response(content_type="text/html", text=content)

async def offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pcs.add(pc)

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        print(f"Connection state is {pc.connectionState}")
        if pc.connectionState == "failed":
            await pc.close()
            pcs.discard(pc)

    @pc.on("track")
    def on_track(track):
        if track.kind == "video":
            print("Video track received")
            # ここで変換トラック(YOLO処理)を噛ませて、addTrackで送り返す設定にする
            local_video = VideoTransformTrack(track)
            pc.addTrack(local_video)

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.json_response({
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    })

async def on_shutdown(app):
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()
    # cv2.destroyAllWindows() # 画面表示を使わないのでこれも不要

if __name__ == "__main__":
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_post("/offer", offer)
    app.on_shutdown.append(on_shutdown)
    web.run_app(app, host="0.0.0.0", port=8080)