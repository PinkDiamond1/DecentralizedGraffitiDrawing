import os
import requests
import cv2
import configparser
import numpy as np
import json


def getPixelWallData():
    try:
        page = requests.get(baseUrl + "graffitiwall")
    except requests.exceptions.RequestException as _:
        print("[getPixelWallData] Can't reach graffitiwall at " + url)
        return
    if page.status_code != 200:
        print("[getPixelWallData] Error fetching wall")
        return
    w = page.json()["data"]
    if type(w) is dict: # if only one pixel
        l = list()
        l.append(w)
        w = l
    return w


def saveSettings():
    if cfg['xres'] == 'original':
        config['GraffitiConfig']['xres'] = 'original'
    else:
        config['GraffitiConfig']['xres'] = str(x_res)
    if cfg['yres'] == 'original':
        config['GraffitiConfig']['yres'] = 'original'
    else:
        config['GraffitiConfig']['yres'] = str(y_res)
    config['GraffitiConfig']['scale'] = str(scale)
    config['GraffitiConfig']['xoffset'] = str(x_offset)
    config['GraffitiConfig']['yoffset'] = str(y_offset)
    config['GraffitiConfig']['interpolation'] = str(int_mode)
    with open('settings.ini', 'w') as cfgfile:
        config.write(cfgfile)
    print('saved')


indices = set()
def loadIndices():
    try:
        page = requests.get(baseUrl + "validator/eth1/" + address)
    except requests.exceptions.RequestException as _:
        print("can't reach graffitiwall")
        return ""
    if not page.ok:
        print(page.text)
        return
    data = page.json()['data']
    if data is None:
        print("Invalid address")
        return
    if type(data) is dict:
        l = list()
        l.append(data)
        data = l
    for validator in data:
        indices.add(validator["validatorindex"])


def paintWall():
    global indices
    if eth1FilterEnabled and len(indices) == 0:
        loadIndices()
    for pixel in wall_data:
        if eth1FilterEnabled and pixel["validator"] not in indices:
            new_pixel = [255, 255, 255]
        else:
            new_pixel = tuple(int(pixel["color"][i:i + 2], 16) for i in (4, 2, 0))  # opencv wants pixels in BGR
        wall[pixel["y"]][pixel["x"]] = new_pixel


counted = False
def paintImage():
    global wall, img, left_pixels, right_pixels, total_pixels, counted
    if hide:
        return
    visible = img[..., 3] != 0
    wall_part = wall[y_offset: y_offset + y_res, x_offset: x_offset + x_res]
    # This looks too complicated. If you know how to do this better, feel free to improve
    same = np.all(img[..., :3] == wall_part, axis=-1)  # correct pixels set to true, but doesn't filter transparent
    correct_pixels = same + ~visible
    need_to_set = ~correct_pixels
    if not counted:
        left_pixels = np.sum(need_to_set)
        total_pixels = np.sum(visible)
        right_pixels = np.sum(correct_pixels) - np.sum(~visible)
        counted = True
    mask2 = np.repeat(need_to_set[..., np.newaxis], 3, axis=2)
    if not progressFilterEnabled:
        np.copyto(wall_part, img[..., :3], where=mask2)
    else:
        np.copyto(wall_part, np.array([0, 0, 255], dtype=np.uint8), where=mask2)
        need_to_not_set = ~(~same + ~visible)
        mask3 = np.repeat(need_to_not_set[..., np.newaxis], 3, axis=2)
        # this now includes white pixels if they're visible (alpha > 0)
        # depending on your input image the output may looks unexpected, but should be correct
        np.copyto(wall_part, np.array([0, 255, 0], dtype=np.uint8), where=mask3)


def getPixelInfo(x, y):
    # very inefficient, #TODO transform wall_data into map or something
    for pixel in wall_data:
        if pixel['y'] == y and pixel['x'] == x:
            info = ""
            info += "x: " + str(x) + "\n"
            info += "y: " + str(y) + "\n"
            info += "RGB: " + pixel['color'] + "\n"
            info += "validator: " + str(pixel['validator']) + "\n"
            info += "slot: " + str(pixel['slot']) + "\n"
            return info
    return ""


def repaint():
    global wall, wall2
    wall = np.full((1000, 1000, 3), 255, np.uint8)
    if overpaint or progressFilterEnabled:
        paintWall()
        paintImage()
    else:
        paintImage()
        paintWall()
    wall2 = wall.copy()


def changeSize(scale_percent=0):
    global x_res, y_res, img, scale

    width = int(x_res * (100 + scale_percent) / 100)
    height = int(y_res * (100 + scale_percent) / 100)

    if width + x_offset > 1000 or \
            height + y_offset > 1000:
        # seems like one border reached, we don't want to change aspect ratio
        return
    x_res = width
    y_res = height
    scale += int(scale_percent * scale / 100)
    img = cv2.resize(orig_img, dsize=(x_res, y_res), interpolation=interpolation_modes[int_mode])
    repaint()


def nextInterpolationMode():
    global int_mode
    found = False
    int_before = int_mode
    for key in interpolation_modes.keys():
        if found:
            int_mode = key
            break
        found = key == int_mode
    if int_before == int_mode:
        int_mode = next(iter(interpolation_modes))
    changeSize()


def changePos(x=0, y=0):
    global x_offset, y_offset
    x_offset = max(0, min(x_offset + x, 1000 - x_res))
    y_offset = max(0, min(y_offset + y, 1000 - y_res))
    repaint()


def toggleOverpaint():
    global overpaint
    overpaint = not overpaint
    repaint()


def toggleHide():
    global hide
    hide = not hide
    repaint()


def toggleProgressFilter():
    global progressFilterEnabled
    progressFilterEnabled = not progressFilterEnabled
    repaint()


def draw_label(text, pos):
    font_face = cv2.FONT_HERSHEY_SIMPLEX
    s = 0.4
    color = (0, 0, 0)  # black
    thickness = cv2.FILLED
    txt_size = cv2.getTextSize(text, font_face, s, thickness)

    for i, line in enumerate(text.split('\n')):
        y2 = pos[1] + i * (txt_size[0][1] + 4)
        cv2.putText(wall2, line, (pos[0], y2), font_face, s, color, 1, 2)


def onMouseEvent(event, x, y, flags, param):
    global wall2
    if event == cv2.EVENT_MOUSEMOVE:
        wall2 = wall.copy()
        pixel_string = getPixelInfo(x, y)
        if pixel_string != "":
            draw_label(pixel_string, (x, y))


def eth2addresses():
    eth2_addresses = set()
    for pixel in wall_data:
        x = pixel["x"]
        y = pixel["y"]
        # 1. is near our image
        if x_offset <= x < x_offset + x_res and \
           y_offset <= y < y_offset + y_res:
            if np.all(tuple(int(pixel["color"][i:i + 2], 16) for i in (4, 2, 0)) == img[y - y_offset, x - x_offset, :3]):
                eth2_addresses.add(str(pixel["validator"]))
    return list(eth2_addresses)


def printHelp():
    print("   ### USAGE ###")
    print("Press buttons while the viewer window is active.")
    print(" h               This help message")
    print(" w, a, s, d      Move image around")
    print(" +, -            Scale image")
    print(" i               Loop through interpolation modes used in image scaling")
    print(" v               Show/hide image")
    print(" o               Enable/disable 'overpaint'. If not active, 'wrong' pixels (by others) are drawn above your image. This could help you selecting an empty spot.")
    print(" p               Enable/disable progress filter. Used to highlight right and wrong pixels which could be hard to detect otherwise.")
    print(" c               Counts how many pixels are needed to draw your image.")
    print(" 1               List execution layer addresses of drawing participants for your image (eg. for POAPs)")
    print(" 2               List validator addresses of drawing participants for your image")
    print(" f               Save your current image configuration to settings.ini")
    print(" e               Export your current image to graffiti.json")
    print(" x               Filter by execution layer address")
    print(" q, ESC          Close application")

def eth1addresses():
    val_addresses = eth2addresses()
    if len(val_addresses) == 0:
        print("No pixels yet")
        return set()
    eth1_addresses = set()
    for i in range(0, len(val_addresses), 100):
        validators = ','.join(val_addresses[i:i+100])
        try:
            page = requests.get(baseUrl + "validator/" + validators + "/deposits")
        except requests.exceptions.RequestException as _:
            print("can't reach graffitiwall")
            return ""
        data = page.json()['data']
        if type(data) is dict:
            eth1_addresses.add(data['from_address'])
        else:
            for validator in data:
                eth1_addresses.add(validator["from_address"])
    
    return eth1_addresses


def toggleAddressFilter():
    global eth1FilterEnabled
    eth1FilterEnabled = not eth1FilterEnabled
    repaint()


def export():
    # we need to loop anyways
    # visible = img[..., 3] != 0
    # in_json = json.dumps(img[np.where(visible)].tolist())
    out_json = list()
    for i in range(img.shape[0]):
        for j in range(img.shape[1]):
            pixel = img[i, j]
            if pixel[3] > 0:
                color = format(pixel[2], '02x')
                color += format(pixel[1], '02x')
                color += format(pixel[0], '02x')
                out_json.append({"x": j + x_offset, "y": i + y_offset, "color": color})
    with open('graffiti.json', 'w') as graffiti_file:
        graffiti_file.write(json.dumps(out_json))
    print("exported " + str(len(out_json)) + " pixels")


def show(title):
    global count
    cv2.namedWindow(title, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(title, onMouseEvent)
    done = False
    print('Config loaded! Press "h" while the viewer window is active to show manuals.')
    while not done:
        cv2.imshow(title, wall2)
        c = cv2.waitKey(1)
        if c == -1:
            continue
        k = chr(c)
        if k == '+':
            changeSize(10)
        elif k == '-':
            changeSize(-10)
        elif k == 'w':
            changePos(0, -10)
        elif k == 'a':
            changePos(-10, 0)
        elif k == 's':
            changePos(0, 10)
        elif k == 'd':
            changePos(10, 0)
        elif k == 'h':
            printHelp()
        elif k == 'o':
            toggleOverpaint()
        elif k == 'v':
            toggleHide()
        elif k == 'p':
            toggleProgressFilter()
        elif k == 'i':
            nextInterpolationMode()
        elif k == 'e':
            export()
        elif k == 'x':
            toggleAddressFilter()
        elif k == 'c':
            print("Total pixels:   " + str(total_pixels) + " (+" + str(x_res * y_res - total_pixels) + " invisible)")
            print("Correct pixels: " + str(right_pixels))
            print("Pixels left:    " + str(left_pixels) + "\n\n")
        elif k == '1':
            print("\n\n --- Participating execution layer addresses: ")
            eth1 = eth1addresses()
            for add in eth1:
                print(add)
            print(" --- " + str(len(eth1)) + " total\n")
        elif k == '2':
            print("\n\n --- Participating validator indices: ")
            eth2 = eth2addresses()
            for add in eth2:
                print(add)
            print(" --- " + str(len(eth2)) + " total\n")
        elif k == 'f':  # c == 19 to ctrl + s, but for qt backend only ?
            saveSettings()
        elif k == 'q' or c == 27:  # esc-key
            done = True
    cv2.destroyAllWindows()


interpolation_modes = {
    "near": cv2.INTER_NEAREST,
    "lin": cv2.INTER_LINEAR,
    "cube": cv2.INTER_CUBIC,
    "area": cv2.INTER_AREA,
    "lanc4": cv2.INTER_LANCZOS4,
    "lin_ex": cv2.INTER_LINEAR_EXACT,
}

if __name__ == "__main__":
    print("Loading your image config from settings.ini... Please wait")
    config = configparser.ConfigParser(inline_comment_prefixes=('#',))
    config.read('settings.ini')
    cfg = config['GraffitiConfig']
    file = cfg['ImagePath']
    if not os.path.isabs(file):
        file = os.path.dirname(os.path.abspath(__file__)) + "/" + file
    orig_img = cv2.imread(file, cv2.IMREAD_UNCHANGED)
    if orig_img is None:
        print("Can't load image " + file)
        exit(1)
    y_res, x_res, channels = orig_img.shape
    scale = int(cfg['scale'])
    x_res = int(x_res * (scale / 100))
    y_res = int(y_res * (scale / 100))
    # absolute resolution is preffered over relative (= scale is ignored if x/y_res is set)
    if cfg['XRes'] != "original":
        x_res = int(cfg['XRes'])
    if cfg['YRes'] != "original":
        y_res = int(cfg['YRes'])
    if cfg['network'] == "mainnet":
        baseUrl = "https://beaconcha.in/api/v1/"
    elif cfg['network'] == "gnosis":
        baseUrl = "https://beacon.gnosischain.com/api/v1/"
    else:
        baseUrl = "https://" + cfg['network'] + ".beaconcha.in/api/v1/"
    img = orig_img
    x_offset = min(1000 - x_res, int(cfg['XOffset']))
    y_offset = min(1000 - y_res, int(cfg['YOffset']))
    overpaint = True
    wall_data = getPixelWallData()
    hide = False
    progressFilterEnabled = False
    eth1FilterEnabled = False
    int_mode = cfg["interpolation"]
    address = cfg["address"]
    if int_mode not in interpolation_modes:
        print("unknown interpolation mode: " + cfg["interpolation"])
        exit(1)

    changeSize()
    show("Beaconcha.in Graffitiwall (" + cfg['network'] + ")")
