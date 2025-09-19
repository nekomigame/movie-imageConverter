import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
from time import sleep
import sys
import subprocess
from PIL import Image
import install_ffmpeg


class ConverterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ファイルコンバーター＆圧縮ツール")
        self.geometry("600x350")

        # --- 変数定義 ---
        self.input_file_path = tk.StringVar()
        self.status_text = tk.StringVar(value="処理するファイルを選択してください。")
        self.mode = tk.StringVar(value="convert")
        self.selected_format = tk.StringVar()
        self.compression_quality = tk.StringVar(value="Medium")
        self.ffmpeg_available = False

        # --- フォーマット定義 ---
        self.image_formats = [
            "png", "jpg", "jpeg", "webp", "gif", "bmp", "tiff",
            "ico", "tga", "pcx", "ppm", "pgm", "pbm"
        ]
        self.video_formats = [
            "mp4", "mkv", "mov", "avi", "wmv", "webm", "flv", "mpg",
            "mpeg", "vob", "ogv", "mts", "ts", "m2ts", "3gp", "f4v"
        ]

        # --- UIコンポーネントの定義 ---
        self.setup_ui()
        # アプリケーション起動時にFFmpegの存在を確認
        self.check_ffmpeg()

    def check_ffmpeg(self):
        """FFmpegが利用可能か確認し、利用不可の場合は警告を表示する"""
        try:
            subprocess.run(
                ["ffmpeg", "-version"],
                check=True,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            self.ffmpeg_available = True
        except (FileNotFoundError, subprocess.CalledProcessError):
            self.ffmpeg_available = False
            if messagebox.askokcancel("FFmpegインストール", "FFmpegが見つかりません。FFmpegをインストールしますか？"):
                install_ffmpeg.download_and_extract()
                print("アプリケーションを再起動してください。")
                sleep(10)
                sys.exit()
            else:
                messagebox.showwarning(
                    "FFmpeg Warning",
                    "FFmpegが見つかりません。PCにインストールし、環境変数PATHに登録してください。\n動画の変換・圧縮機能は利用できません。"
                )

    def setup_ui(self):
        # --- ファイル選択フレーム ---
        file_frame = ttk.LabelFrame(self, text="1. ファイル選択", padding=(10, 5))
        file_frame.pack(fill=tk.X, padx=10, pady=5)

        file_entry = ttk.Entry(
            file_frame, textvariable=self.input_file_path, state="readonly", width=60)
        file_entry.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5, pady=5)
        browse_button = ttk.Button(
            file_frame, text="選択...", command=self.select_file)
        browse_button.pack(side=tk.LEFT, padx=5, pady=5)

        # --- モード選択フレーム ---
        mode_frame = ttk.LabelFrame(self, text="2. モード選択", padding=(10, 5))
        mode_frame.pack(fill=tk.X, padx=10, pady=5)

        convert_radio = ttk.Radiobutton(
            mode_frame, text="拡張子変換", variable=self.mode, value="convert", command=self.toggle_mode)
        convert_radio.pack(side=tk.LEFT, padx=10)
        compress_radio = ttk.Radiobutton(
            mode_frame, text="ファイル圧縮", variable=self.mode, value="compress", command=self.toggle_mode)
        compress_radio.pack(side=tk.LEFT, padx=10)

        # --- オプションフレーム ---
        self.options_container = tk.Frame(self)
        self.options_container.pack(fill=tk.X, padx=10, pady=5)

        # 変換オプション
        self.convert_frame = ttk.LabelFrame(
            self.options_container, text="3. 変換オプション", padding=(10, 5))
        format_label = ttk.Label(self.convert_frame, text="変換後フォーマット:")
        format_label.pack(side=tk.LEFT, padx=5)
        self.format_menu = ttk.Combobox(
            self.convert_frame, textvariable=self.selected_format, state="disabled", width=10)
        self.format_menu.pack(side=tk.LEFT, padx=5)

        # 圧縮オプション
        self.compress_frame = ttk.LabelFrame(
            self.options_container, text="3. 圧縮オプション", padding=(10, 5))
        quality_label = ttk.Label(self.compress_frame, text="品質:")
        quality_label.pack(side=tk.LEFT, padx=5)
        self.quality_menu = ttk.Combobox(
            self.compress_frame, textvariable=self.compression_quality, state="readonly", values=["High", "Medium", "Low"])
        self.quality_menu.pack(side=tk.LEFT, padx=5)

        # --- 実行フレーム ---
        execute_frame = tk.Frame(self)
        execute_frame.pack(fill=tk.X, padx=10, pady=10)
        self.execute_button = ttk.Button(
            execute_frame, text="実行", command=self.execute_task, state="disabled")
        self.execute_button.pack(pady=5)

        # --- ステータス表示 ---
        status_label = ttk.Label(
            self, textvariable=self.status_text, foreground="gray", anchor="w")
        status_label.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=5)

        self.toggle_mode()  # 初期表示を設定

    def toggle_mode(self):
        mode = self.mode.get()
        if mode == "convert":
            self.compress_frame.pack_forget()
            self.convert_frame.pack(fill=tk.X)
        else:  # compress
            self.convert_frame.pack_forget()
            self.compress_frame.pack(fill=tk.X)

        # ファイルが選択されていればボタンを有効化
        if self.input_file_path.get():
            self.execute_button["state"] = "normal"

    def select_file(self):
        video_ext_str = " ".join([f"*.{ext}" for ext in self.video_formats])
        image_ext_str = " ".join([f"*.{ext}" for ext in self.image_formats])
        filetypes = [
            ("対応ファイル", f"{video_ext_str} {image_ext_str}"), ("すべてのファイル", "*.* ")]

        filepath = filedialog.askopenfilename(filetypes=filetypes)
        if not filepath:
            return

        self.input_file_path.set(filepath)
        self.status_text.set(f"選択中: {os.path.basename(filepath)}")

        self.update_format_options()
        self.toggle_mode()

    def update_format_options(self):
        ext = self.input_file_path.get().split('.')[-1].lower()
        target_formats = []
        if ext in self.image_formats:
            target_formats = [f for f in self.image_formats if f != ext]
        elif ext in self.video_formats:
            target_formats = [f for f in self.video_formats if f != ext]

        self.format_menu["values"] = target_formats
        if target_formats:
            self.selected_format.set(target_formats[0])
            self.format_menu["state"] = "readonly"
        else:
            self.selected_format.set("")
            self.format_menu["state"] = "disabled"
            self.status_text.set("エラー: 対応していないファイル形式です。")

    def execute_task(self):
        if not self.input_file_path.get():
            messagebox.showerror("エラー", "ファイルが選択されていません。")
            return

        self.execute_button["state"] = "disabled"
        self.status_text.set("処理を実行中...")
        self.update_idletasks()

        try:
            if self.mode.get() == "convert":
                self.convert_file()
            else:
                self.compress_file()
        except Exception as e:
            self.status_text.set(f"エラー: {e}")
            messagebox.showerror("エラー", f"処理中にエラーが発生しました:\n{e}")
        finally:
            # 正常終了時のみ入力ファイルパスをクリア
            if "完了" in self.status_text.get():
                self.input_file_path.set("")
                self.status_text.set("処理するファイルを選択してください。")
            self.execute_button["state"] = "normal" if self.input_file_path.get(
            ) else "disabled"

    def convert_file(self):
        input_path = self.input_file_path.get()
        target_ext = self.selected_format.get()
        if not target_ext:
            raise ValueError("変換後のフォーマットが選択されていません。")

        directory, filename = os.path.split(input_path)
        name_without_ext = os.path.splitext(filename)[0]
        output_path = os.path.join(
            directory, f"{name_without_ext}.{target_ext}")

        self.status_text.set(f"変換中... -> {os.path.basename(output_path)}")
        self.update_idletasks()

        self._run_process(input_path, output_path)
        self.status_text.set(f"変換完了: {os.path.basename(output_path)}")
        messagebox.showinfo("成功", f"ファイルの変換が完了しました。\n保存先: {output_path}")

    def compress_file(self):
        input_path = self.input_file_path.get()
        quality = self.compression_quality.get()

        directory, filename = os.path.split(input_path)
        name, ext = os.path.splitext(filename)
        output_path = os.path.join(directory, f"{name}_compressed{ext}")

        self.status_text.set(f"圧縮中... -> {os.path.basename(output_path)}")
        self.update_idletasks()

        self._run_process(input_path, output_path, quality)
        self.status_text.set(f"圧縮完了: {os.path.basename(output_path)}")
        messagebox.showinfo("成功", f"ファイルの圧縮が完了しました。\n保存先: {output_path}")

    def _run_process(self, input_path, output_path, quality=None):
        input_ext = input_path.split('.')[-1].lower()
        if input_ext in self.image_formats:
            self._process_image(input_path, output_path, quality)
        elif input_ext in self.video_formats:
            if not self.ffmpeg_available:
                raise RuntimeError("FFmpegが利用できないため、動画処理を実行できません。")
            self._process_video(input_path, output_path, quality)
        else:
            raise ValueError("対応していないファイル形式です。")

    def _process_image(self, input_path, output_path, quality):
        with Image.open(input_path) as img:
            options = {}
            output_ext = output_path.split('.')[-1].lower()

            if quality:
                quality_map = {"High": 90, "Medium": 75, "Low": 50}
                options['quality'] = quality_map.get(quality, 75)

            if output_ext in ('jpg', 'jpeg') and img.mode == 'RGBA':
                img = img.convert('RGB')

            img.save(output_path, **options)

    def _process_video(self, input_path, output_path, quality):
        command = ["ffmpeg", "-i", input_path, "-y"]
        if quality:
            crf_map = {"High": 20, "Medium": 25, "Low": 30}
            command.extend(["-c:v", "libx264", "-crf",
                           str(crf_map.get(quality, 25))])

        command.append(output_path)

        try:
            subprocess.run(command, check=True, capture_output=True,
                           text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        except FileNotFoundError:
            raise FileNotFoundError(
                "FFmpegが見つかりません。PCにインストールし、環境変数PATHに登録してください。")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"FFmpegエラー:\n{e.stderr}")


if __name__ == "__main__":
    app = ConverterApp()
    app.mainloop()
