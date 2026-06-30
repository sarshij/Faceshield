import asyncio
import httpx
import os
import time
from main import app

async def run_test():
    print("Testing FaceShield API pipeline...")
    
    if not os.path.exists("test_video.mp4"):
        print("test_video.mp4 not found. Please create it first.")
        return
        
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Upload
        print("\n1. Uploading video...")
        with open("test_video.mp4", "rb") as f:
            files = {'file': ('test_video.mp4', f, 'video/mp4')}
            response = await client.post("/api/upload", files=files)
            
        print(f"Upload Status: {response.status_code}")
        if response.status_code != 200:
            print(f"Error: {response.text}")
            return
            
        data = response.json()
        session_id = data["session_id"]
        print(f"Session ID: {session_id}")
        print(f"Metadata: {data['metadata']}")
        
        # 2. Detect
        print("\n2. Triggering detection...")
        response = await client.post("/api/detect", json={"session_id": session_id})

        print(f"Detect Status: {response.status_code}")
        if response.status_code != 200:
            print(f"Error: {response.text}")
            return
            
        faces_data = response.json()
        faces = faces_data.get("faces", [])
        print(f"Detected {len(faces)} faces.")
        
        # Since the test video might not have real faces, let's add a manual region
        print("\n3. Adding manual region...")
        response = await client.post("/api/add-region", json={
            "session_id": session_id,
            "x": 100,
            "y": 100,
            "w": 100,
            "h": 100,
            "frame_number": 0
        })
        print(f"Add Region Status: {response.status_code}")
        if response.status_code != 200:
            print(f"Error: {response.text}")
            return
            
        region_data = response.json()
        face_id = region_data["id"]
        print(f"Manual region added: {face_id}")
        
        # 4. Process
        print("\n4. Starting processing...")
        response = await client.post("/api/process", json={
            "session_id": session_id,
            "selected_face_ids": [face_id],
            "blur_type": "pixelate",
            "blur_intensity": 50,
            "output_format": "mp4"
        })
        print(f"Process Status: {response.status_code}")
        if response.status_code != 200:
            print(f"Error: {response.text}")
            return
            
        # 5. Monitor progress via SSE (roughly)
        print("\n5. Polling progress (simulated SSE)...")
        # We can't easily test SSE with httpx without a special stream reader,
        # but the background task updates the session in memory.
        # We can just check the preview endpoint until it succeeds (meaning it's done).
        for _ in range(20):
            response = await client.get(f"/api/preview/{session_id}")
            if response.status_code == 200:
                print("Processing complete! Preview available.")
                break
            print("Still processing...")
            await asyncio.sleep(2)
        else:
            print("Processing timed out or failed.")
            
        # 6. Check download
        print("\n6. Checking download...")
        response = await client.get(f"/api/download/{session_id}")
        print(f"Download Status: {response.status_code}")
        if response.status_code == 200:
            print(f"Success! Output size: {len(response.content)} bytes")
        else:
            print(f"Download failed: {response.text}")
            
if __name__ == "__main__":
    asyncio.run(run_test())
