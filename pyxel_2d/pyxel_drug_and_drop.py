import pyxel
import math

class App:
    # 現在表示している文字の位置を保持するクラス変数
    _text_index = 0

    def __init__(self):
      pyxel.init(256, 256, title="test")
      pyxel.mouse(True)

      self.moving_box_idx = None

      self.box_list = [(128,128,(20,20)),(64,64,(20,20)),(32,128,(30,30)),(134,43,(40,40))]


      pyxel.run(self.update, self.draw)

    def update(self):
        if pyxel.btnp(pyxel.MOUSE_BUTTON_LEFT):
            for i, (box_x,box_y,size) in enumerate(self.box_list):
                width, height = size[0], size[1]
                if self.is_covered(box_x-(width//2),box_y-(height//2),size):
                    self.moving_box_idx = i
        elif pyxel.btn(pyxel.MOUSE_BUTTON_LEFT):
            if self.moving_box_idx is not None:
                size = self.box_list[self.moving_box_idx][2]
                self.box_list[self.moving_box_idx] = (pyxel.mouse_x,pyxel.mouse_y,size)
        elif pyxel.btnr(pyxel.MOUSE_BUTTON_LEFT):
            self.moving_box_idx = None

    def draw(self):
      pyxel.cls(0)
      if self.box_list:
          for x,y,size in self.box_list:
              self.rect_draw(x,y,size)

    def rect_draw(self, x, y, size):
        width, height = size[0], size[1]
        pyxel.rect(x - (width//2), y - (height//2), width, height, 11)

    def is_covered(self,box_x,box_y,size):
        width, height = size[0], size[1]
        return box_x <= pyxel.mouse_x <= (box_x + width) and box_y <= pyxel.mouse_y <= (box_y + height)
        
App()