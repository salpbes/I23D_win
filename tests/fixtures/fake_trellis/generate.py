import argparse, shutil, sys, time, os
p = argparse.ArgumentParser(); p.add_argument("image"); p.add_argument("--output"); p.add_argument("--seed")
p.add_argument("--no-texture", action="store_true"); p.add_argument("--texture-size"); p.add_argument("--pipeline-type", choices=["512","1024","1024_cascade"])
a = p.parse_args()
if os.environ.get("FAKE_FAIL"): print("Traceback ...\nImportError: boom"); sys.exit(1)
print("="*60); print("TRELLIS.2 on Apple Silicon"); print("\nLoading pipeline...")
sys.stderr.write("model.safetensors: downloading bytes: 50%\r"); sys.stderr.flush()
for stage in ("Sampling sparse structure", "Sampling shape SLat", "Sampling texture SLat"):
    for i in range(0, 13, 4):
        sys.stderr.write(f"\r{stage}: {int(i/12*100):3d}%|###| {i}/12 [00:01<00:00]"); sys.stderr.flush(); time.sleep(0.05)
    sys.stderr.write("\n")
print("\nMesh: 1,308,352 vertices, 2,703,762 triangles")
print("Exporting with vertex colors (use --texture-size for PBR textures)...")
shutil.copy(os.path.join(os.path.dirname(__file__), "..", "messy.glb"), a.output + ".glb")
print(f"Saved: {a.output}.glb")
