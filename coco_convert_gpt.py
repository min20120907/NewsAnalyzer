import os
import json
import sys
import cv2
import numpy as np
from zipfile import ZipFile
import glob
from multiprocessing import Pool
import read_roi
import time
from tqdm import tqdm
from os.path import dirname
from argparse import ArgumentParser
from sympy import Symbol, solve

coco_path = ""
txt = ""
default_file_name = "via_region_data.json"
mode = ""
append_mode = False
# tmp_dir = ""
import shutil

def rename_file(src_file, dst_file):
    shutil.move(src_file, dst_file)

def process_file(args):
    zip_file, filename, json_name, folder = args
    original={}
    roi = read_roi.read_roi_zip( zip_file)
    roi_list = list(roi.values())

    im = cv2.imread( filename)
    h, w, c = im.shape
    size = os.path.getsize( filename)

    try:
        with open(json_name) as f:
            original = json.loads(f.read())
    except ValueError:
        print('Decoding JSON has failed')
    except FileNotFoundError:
        original = {}

    data = {
        filename + str(size): {
            "fileref": "",
            "size": size,
            "filename": filename,
            "base64_img_data": "",
            "file_attributes": {},
            "regions": {},
        }
    }
    for a in roi_list:
        try:
            filename2 = filename.replace(txt, "").replace("-", " ").split(" ")
            roi_name = a["name"].replace("-", " ").split(" ")
            roi_num =int(roi_name[0])
            file_num = int(filename2[-1])
            has_zero = False
            if has_zero:
                roi_num-=1
            if file_num == roi_num:
                x_list = a["x"]
                y_list = a["y"]
                for l in range(len(x_list)):
                    if x_list[l] >= w:
                        x_list[l] = w
                for k in range(len(y_list)):
                    if y_list[k] >=h:
                        y_list[k] = h
                x_list.append(a["x"][0])
                y_list.append(a["y"][0])
                regions = {
                    str(a): {
                        "shape_attributes": {
                            "name": "polygon",
                            "all_points_x": x_list,
                            "all_points_y": y_list,
                        },
                        "region_attributes": {"name": dirname(folder)},
                    }
                }
                data[filename + str(size)]["regions"].update(regions)
                original.update(data)
        except KeyError:
            if a['type']=="line":
                x1 = a['x1']
                x2 = a['x2']
                y1 = a['y1']
                y2 = a['y2']
                width = a['width']
                new_x_list =[]
                new_y_list =[]
                if (x1-x2)==0:
                    slope = 0
                else:
                    slope = (y1-y2)/(x1-x2)
                    slope_a = (-1)/slope
                midpoint=[(x1+x2)/2, (y1+y2)/2]
                x = Symbol('x')
                weight = solve(x**2+(x*slope_a)**2- (width/2)**2, x)
                new_x_list.append(int(x1-(weight[1])))
                new_x_list.append(int(x1+(weight[1])))
                new_x_list.append(int(x2-(weight[0])))
                new_x_list.append(int(x2+(weight[0])))
                new_x_list.append(int(x1-(weight[1])))
                for j in range(len(new_x_list)):
                    if(new_x_list[j]>=2160):
                        new_x_list[j] = 2159
                for k in range(len(new_y_list)):
                    if(new_y_list[k]>=2160):
                        new_y_list[k] = 2159
                regions = {
                    str(a): {
                        "shape_attributes": {
                            "name":  "polygon",
                            "all_points_x": new_x_list,
                            "all_points_y": new_y_list
                        },
                        "region_attributes": {
                            "name": dirname(folder)
                        }
                    } 
                }
                data[filename + str(size)]["regions"].update(regions)
                original.update(data)
            elif a['type']=="oval":
                TWO_PI=np.pi*2
                angles = 128
                angle_shift = TWO_PI/ angles
                phi = 0
                center_x = (2*(a['left']) + a['width'])/2
                center_y = (2 * a['top'] + a['height'])/2
                x_list = []
                y_list = []
                for i in range(angles):
                    phi+=angle_shift
                    x_list.append(int(center_x + (a['width'] * np.cos(phi)/2)))
                    y_list.append(int(center_y + (a['height'] * np.sin(phi)/2)))
                regions = {
                    str(a): {
                        "shape_attributes": {
                            "name": "polygon",
                            "all_points_x": x_list,
                            "all_points_y": y_list,
                        },
                        "region_attributes": {
                             "name": dirname(folder),
                             "class": "cell"},
                    }
                
                }
                data[filename + str(size)]["regions"].update(regions)
                original.update(data)
                    
        except IndexError or FileNotFoundError:
            print("[ERROR] Can't find any type specific files! (Maybe check the file type)") 
    with open(json_name, "w", encoding="utf-8") as f:
        f.write(json.dumps(original, ensure_ascii=False))

    return json_name


def process_folder(coco_path):
    global txt, default_file_name, mode, append_mode, tmp_dir
    
    #if tmp_dir:
    #    new_folder = os.path.join(tmp_dir, os.path.basename(coco_path))
    #    if not os.path.exists(new_folder):
    #        os.makedirs(new_folder)
    #    for filename in os.listdir(coco_path):
    #        src_file = os.path.join(coco_path, filename)
    #        dst_file = os.path.join(new_folder, filename)
    #        rename_file(src_file, dst_file)
    #    coco_path = tmp_dir
    
    args1 = []
    for r, d, f in os.walk(coco_path):
        filenames = []
        zips = []
        for file in f:
            if os.path.splitext(file)[-1] == txt:
                filenames.append(os.path.join(r, file))
            elif os.path.splitext(file)[-1] == ".zip":
                zips.append(os.path.join(r, file))

        for filename in filenames:
            for zip_file in zips:
                json_name = os.path.splitext(filename)[0] + "_" + os.path.splitext(os.path.basename(zip_file))[0] + ".json"
                json_name = os.path.join(os.path.dirname(filename), json_name)
                if append_mode and os.path.exists(json_name):
                    continue
                args1.append((zip_file, filename, json_name, os.path.dirname(filename)))


    print("Scanning completed!")
    start_time = time.time()

    with Pool(processes=os.cpu_count()) as pool:
        results = list(tqdm(pool.imap_unordered(process_file, args1), total=len(args1)))

    result = {}
    print("Combining...")

    for f in tqdm(glob.glob(os.path.join(os.path.dirname(coco_path), "*.json") if mode == "single" else os.path.join(os.path.dirname(coco_path), "*", "*.json"))):
        with open(f, "r") as infile:
            try:
                result.update(json.load(infile))
            except:
                pass

    with open(os.path.join(os.path.join( coco_path, os.path.pardir) if mode == "single" else coco_path, default_file_name), "a" if mode == "single" else "w" ) as outfile:
        try:
            json.dump(result, outfile)
        except:
            pass

    
    #if tmp_dir:
    #    for filename in os.listdir(new_folder):
    #        src_file = os.path.join(new_folder, filename)
    #        dst_file = os.path.join(os.path.dirname(coco_path), filename)
    #        rename_file(src_file, dst_file)
    #    os.rmdir(new_folder)
    print("Cleaning...")
    for f in tqdm(glob.glob(os.path.join(os.path.join(os.path.dirname(coco_path), "*.json")) if mode == "single" else os.path.join(os.path.dirname(coco_path), "*", "*.json"))):
        if os.path.basename(f) != default_file_name:
            os.remove(f)
    print("---CONVERT ENDED----")
    print("---" + str(time.time() - start_time) + "secs ----")
    return result

    
if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--coco_path", type=str, required=True, help="Path to COCO dataset")
    parser.add_argument("--txt", type=str, required=True, help="File extension to look for")
    parser.add_argument("--mode", type=str, default="batch", help="Mode: single or batch")
    parser.add_argument("--append_mode", action='store_true', help="Whether to append to existing JSON file or create new file")
    # parser.add_argument("--tmp_dir", type=str, default="", help="Directory to use for temporary files")
    parser.add_argument("--json_file", type=str, default=default_file_name, help="JSON file name (default: 'via_region_data.json')")
    args = parser.parse_args()

    coco_path = args.coco_path
    txt = args.txt
    mode = args.mode
    append_mode = args.append_mode
    # tmp_dir = args.tmp_dir
    default_file_name = args.json_file

    if mode == "single":
        process_folder(os.path.join(coco_path))
    else:
        for folder in os.listdir(coco_path):
            if os.path.isdir(os.path.join(coco_path, folder)):
                process_folder(folder)

