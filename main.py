import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
import sys
import subprocess
from PIL import Image
import threading
from queue import Queue, Empty
import shutil
import tempfile
import traceback

# install_ffmpegがない場合のエラーハンドリング
try:
    import install_ffmpeg
except ImportError:
    install_ffmpeg = None

class ConverterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ファイルコンバーター＆圧縮ツール")
        self.geometry("600x650") # 少し高さを広げた
        
        # WindowsでのDPIスケーリング対応
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except:
            pass

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # --- 変数定義 ---
        self.input_file_path = tk.StringVar()
        self.file_info_text = tk.StringVar(value="ファイル未選択")
        self.status_text = tk.StringVar(value="処理するファイルを選択してください。")
        self.mode = tk.StringVar(value="convert")
        self.selected_format = tk.StringVar()
        self.target_size_mb = tk.StringVar(value="10")
        self.selected_encoder = tk.StringVar()
        self.quality_var = tk.StringVar(value="Medium")
        self.available_encoders = []
        self.task_queue = Queue()
        self.worker_thread = None
        self.current_process = None
        self.cancel_requested = False
        
        self.ffmpeg_path = None
        self.ffprobe_path = None

        # --- フォーマット定義 ---
        self.image_formats = [
            "png", "jpg", "jpeg", "webp", "gif", "bmp", "tiff",
            "ico", "tga", "ppm"
        ]
        
        self.video_formats = [
            "mp4", "mkv", "mov", "avi", "wmv", "webm", "flv", "mpg", "mpeg", 
            "ts", "m2ts", "3gp", "3g2", "m4v", "vob", "ogv", "mts", "mxf",
            "rm", "rmvb", "asf", "amv", "divx", "f4v", "m2v", "mpe", "mpv", 
            "mpeg1", "mpeg2", "mpeg4", "ogm", "ogx", "dv", "drc", "gvi", 
            "iso", "m1v", "tod", "vro", "wtv", "xesc", "bin", "nsv", "nuv", "rec"
        ]

        self.setup_style()
        self.locate_binaries()
        self.setup_ui()
        
        if self.ffmpeg_path:
            self.detect_encoders()
        else:
            self.after(500, self.check_and_install_ffmpeg)

    def setup_style(self):
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
        elif "winnative" in style.theme_names():
            style.theme_use("winnative")
            
        style.configure("TButton", padding=6)
        style.configure("TLabel", padding=2)
        style.configure("TLabelframe", padding=10)
        style.configure("Big.TButton", font=("Meiryo UI", 11, "bold"), padding=10)

    def on_closing(self):
        if self.worker_thread and self.worker_thread.is_alive():
            if messagebox.askokcancel("終了確認", "処理が実行中です。強制終了しますか？"):
                self.cancel_task()
                self.destroy()
        else:
            self.destroy()

    def get_base_dir(self):
        """実行環境に応じたベースディレクトリを取得"""
        if getattr(sys, 'frozen', False):
            return os.path.dirname(sys.executable)
        else:
            return os.path.dirname(os.path.abspath(__file__))

    def locate_binaries(self):
        """FFmpeg/FFprobeを探す"""
        base_dir = self.get_base_dir()
        local_ffmpeg = os.path.join(base_dir, "ffmpeg.exe")
        local_ffprobe = os.path.join(base_dir, "ffprobe.exe")
        
        if os.path.exists(local_ffmpeg):
            self.ffmpeg_path = local_ffmpeg
        else:
            self.ffmpeg_path = shutil.which("ffmpeg")

        if os.path.exists(local_ffprobe):
            self.ffprobe_path = local_ffprobe
        else:
            self.ffprobe_path = shutil.which("ffprobe")

    def check_and_install_ffmpeg(self):
        if not self.ffmpeg_path:
            self.available_encoders = [("CPU (libx264)", "libx264")]
            if install_ffmpeg:
                if messagebox.askyesno("FFmpeg不足", "動画処理に必要なFFmpegが見つかりません。\n自動的にダウンロードしてインストールしますか？"):
                    self.status_text.set("FFmpegをダウンロード中...")
                    self.execute_button["state"] = "disabled"
                    threading.Thread(target=self._download_ffmpeg_thread, daemon=True).start()
                else:
                    self.status_text.set("警告: FFmpegがないため、動画機能は制限されます。")
            else:
                self.status_text.set("警告: FFmpegが見つかりません。手動でインストールしてください。")

    def _download_ffmpeg_thread(self):
        if not install_ffmpeg: return
        try:
            def progress_callback(msg):
                self.task_queue.put(("status", msg))
            install_ffmpeg.download_and_extract(progress_callback=progress_callback)
            self.task_queue.put(("ffmpeg_installed", None))
        except Exception as e:
            self.task_queue.put(("error", f"ダウンロードエラー: {e}"))

    def detect_encoders(self):
        """エンコーダー検出"""
        self.available_encoders = [("CPU (libx264)", "libx264")]
        if self.ffmpeg_path:
            try:
                # Windows固有のウィンドウ非表示設定
                startupinfo = None
                if os.name == 'nt':
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

                result = subprocess.run(
                    [self.ffmpeg_path, "-encoders"],
                    capture_output=True, text=True, check=True,
                    startupinfo=startupinfo, encoding='utf-8', errors='ignore'
                )
                output = result.stdout
                
                if "h264_nvenc" in output:
                    self.available_encoders.append(("Nvidia GPU (nvenc)", "h264_nvenc"))
                if "h264_qsv" in output:
                    self.available_encoders.append(("Intel GPU (qsv)", "h264_qsv"))
                if "h264_amf" in output:
                    self.available_encoders.append(("AMD GPU (amf)", "h264_amf"))
            except Exception:
                pass 
        self.update_encoder_menu()

    def update_encoder_menu(self):
        menu_values = [name for name, codec in self.available_encoders]
        
        if hasattr(self, 'encoder_menu_compress'):
            self.encoder_menu_compress["values"] = menu_values
        if hasattr(self, 'encoder_menu_convert'):
            self.encoder_menu_convert["values"] = menu_values

        if menu_values and not self.selected_encoder.get():
            self.selected_encoder.set(menu_values[0])
        elif self.selected_encoder.get() not in menu_values:
             if menu_values: self.selected_encoder.set(menu_values[0])

    def setup_ui(self):
        main_frame = ttk.Frame(self, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 1. ファイル選択
        file_frame = ttk.LabelFrame(main_frame, text="1. ファイルを選択", padding=(15, 10))
        file_frame.pack(fill=tk.X, pady=(0, 15))

        input_row = ttk.Frame(file_frame)
        input_row.pack(fill=tk.X)
        
        self.file_entry = ttk.Entry(input_row, textvariable=self.input_file_path, state="readonly", font=("Meiryo UI", 10))
        self.file_entry.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 10))
        
        browse_btn = ttk.Button(input_row, text="参照...", command=self.select_file, width=10)
        browse_btn.pack(side=tk.LEFT)

        self.info_label = ttk.Label(file_frame, textvariable=self.file_info_text, foreground="gray", font=("Meiryo UI", 9))
        self.info_label.pack(anchor="w", pady=(5, 0))

        # 2. 設定エリア
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=(0, 15))

        self.tab_convert = ttk.Frame(self.notebook, padding=15)
        self.notebook.add(self.tab_convert, text='  フォーマット変換 / 画質変更  ')
        self.setup_convert_tab(self.tab_convert)

        self.tab_compress = ttk.Frame(self.notebook, padding=15)
        self.notebook.add(self.tab_compress, text='  サイズ指定圧縮  ')
        self.setup_compress_tab(self.tab_compress)
        
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_change)

        # 3. 実行エリア
        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill=tk.X, side=tk.BOTTOM)

        self.progressbar = ttk.Progressbar(action_frame, mode='indeterminate')
        self.progressbar.pack(fill=tk.X, pady=(0, 10))

        btn_grid = ttk.Frame(action_frame)
        btn_grid.pack(fill=tk.X)
        
        self.execute_button = ttk.Button(
            btn_grid, text="変換を開始", command=self.execute_task, state="disabled", style="Big.TButton")
        self.execute_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 5))

        self.cancel_button = ttk.Button(
            btn_grid, text="中止", command=self.cancel_task, state="disabled")
        self.cancel_button.pack(side=tk.LEFT, fill=tk.Y)

        status_bar = ttk.Label(self, textvariable=self.status_text, relief="sunken", anchor="w", padding=(5, 2))
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.update_encoder_menu()
        self.process_queue()

    def setup_convert_tab(self, parent):
        grid_frame = ttk.Frame(parent)
        grid_frame.pack(fill=tk.X)
        grid_frame.columnconfigure(1, weight=1)

        ttk.Label(grid_frame, text="変換後の形式:", font=("Meiryo UI", 10, "bold")).grid(row=0, column=0, sticky="w", pady=10)
        self.format_menu = ttk.Combobox(grid_frame, textvariable=self.selected_format, state="disabled", width=15, font=("Meiryo UI", 10))
        self.format_menu.grid(row=0, column=1, sticky="w", padx=10, pady=10)
        ttk.Label(grid_frame, text="(現在の拡張子も選択可能)").grid(row=0, column=2, sticky="w")

        ttk.Label(grid_frame, text="画質設定:", font=("Meiryo UI", 10, "bold")).grid(row=1, column=0, sticky="w", pady=10)
        quality_menu = ttk.Combobox(
            grid_frame, textvariable=self.quality_var, 
            values=["Original", "High", "Medium", "Low"], state="readonly", width=15, font=("Meiryo UI", 10))
        quality_menu.grid(row=1, column=1, sticky="w", padx=10, pady=10)
        ttk.Label(grid_frame, text="※Originalは可能な限り無劣化コピー").grid(row=1, column=2, sticky="w")

        ttk.Label(grid_frame, text="エンコーダー:", font=("Meiryo UI", 10, "bold")).grid(row=2, column=0, sticky="w", pady=10)
        self.encoder_menu_convert = ttk.Combobox(
            grid_frame, textvariable=self.selected_encoder, state="readonly", width=30, font=("Meiryo UI", 10))
        self.encoder_menu_convert.grid(row=2, column=1, columnspan=2, sticky="w", padx=10, pady=10)
        ttk.Label(grid_frame, text="※動画変換時のみ有効").grid(row=3, column=1, sticky="w", padx=10)

    def setup_compress_tab(self, parent):
        grid_frame = ttk.Frame(parent)
        grid_frame.pack(fill=tk.X)
        grid_frame.columnconfigure(1, weight=1)

        ttk.Label(grid_frame, text="目標ファイルサイズ:", font=("Meiryo UI", 10, "bold")).grid(row=0, column=0, sticky="w", pady=10)
        size_box = ttk.Frame(grid_frame)
        size_box.grid(row=0, column=1, sticky="w", padx=10, pady=10)
        
        ttk.Entry(size_box, textvariable=self.target_size_mb, width=10, font=("Meiryo UI", 10)).pack(side=tk.LEFT)
        ttk.Label(size_box, text="MB").pack(side=tk.LEFT, padx=5)

        ttk.Label(grid_frame, text="エンコーダー:", font=("Meiryo UI", 10, "bold")).grid(row=1, column=0, sticky="w", pady=10)
        self.encoder_menu_compress = ttk.Combobox(
            grid_frame, textvariable=self.selected_encoder, state="readonly", width=30, font=("Meiryo UI", 10))
        self.encoder_menu_compress.grid(row=1, column=1, sticky="w", padx=10, pady=10)
        
        info_lbl = ttk.Label(grid_frame, text="※2パスエンコードを行い、指定サイズに近づけます。\n※処理に通常の2倍の時間がかかります。", foreground="#555")
        info_lbl.grid(row=2, column=0, columnspan=2, sticky="w", pady=20)

    def on_tab_change(self, event):
        current_tab = self.notebook.index(self.notebook.select())
        self.mode.set("convert" if current_tab == 0 else "compress")

    def update_file_info(self, filepath):
        try:
            size_bytes = os.path.getsize(filepath)
            size_mb = size_bytes / (1024 * 1024)
            ext = os.path.splitext(filepath)[1].lower()
            
            info = f"サイズ: {size_mb:.2f} MB | 形式: {ext}"
            
            if ext.replace('.', '') in self.image_formats:
                try:
                    with Image.open(filepath) as img:
                        info += f" | 解像度: {img.width}x{img.height}"
                except:
                    pass
            
            self.file_info_text.set(info)
            self.info_label.config(foreground="#005500")
        except Exception:
            self.file_info_text.set("ファイル情報の取得に失敗しました")
            self.info_label.config(foreground="red")

    def select_file(self):
        media_exts = []
        media_exts.extend([f"*.{ext}" for ext in self.video_formats])
        media_exts.extend([f"*.{ext}" for ext in self.image_formats])
        
        filetypes = [
            ("メディアファイル", " ".join(media_exts)),
            ("すべてのファイル", "*.*")
        ]

        filepath = filedialog.askopenfilename(filetypes=filetypes)
        if not filepath: return

        self.input_file_path.set(filepath)
        self.status_text.set(f"選択中: {os.path.basename(filepath)}")
        self.update_format_options()
        self.update_file_info(filepath)
        self.execute_button["state"] = "normal"

    def update_format_options(self):
        ext = self.input_file_path.get().split('.')[-1].lower()
        target_formats = []
        
        if ext.replace('.', '') in self.image_formats:
            target_formats = [f for f in self.image_formats]
        else:
            common_outputs = ["mp4", "mkv", "mov", "avi", "webm", "flv", "gif"]
            target_formats = [f for f in common_outputs]
            if ext.replace('.', '') not in target_formats:
                target_formats.append(ext.replace('.', ''))

        self.format_menu["values"] = target_formats
        self.format_menu["state"] = "normal"
        # コンボボックスにピリオドなしで設定
        current_ext = ext.replace('.', '')
        self.selected_format.set(current_ext)

    def execute_task(self):
        if not self.input_file_path.get():
            messagebox.showerror("エラー", "ファイルが選択されていません。")
            return

        params = {
            "mode": self.mode.get(),
            "input_path": self.input_file_path.get(),
            "target_ext": self.selected_format.get(),
            "target_size_mb": self.target_size_mb.get(),
            "selected_encoder": self.selected_encoder.get(),
            "quality": self.quality_var.get()
        }

        self.execute_button["state"] = "disabled"
        self.cancel_button["state"] = "normal"
        self.progressbar.start(10)
        self.status_text.set("処理を開始します...")
        self.cancel_requested = False
        
        # 古いキューをクリア
        while not self.task_queue.empty():
            try: self.task_queue.get_nowait()
            except Empty: break

        self.worker_thread = threading.Thread(target=self._execute_task_threaded, args=(params,))
        self.worker_thread.daemon = True
        self.worker_thread.start()

    def cancel_task(self):
        if self.worker_thread and self.worker_thread.is_alive():
            if messagebox.askokcancel("確認", "処理を中止しますか？"):
                self.cancel_requested = True
                self.status_text.set("中止処理中...")
                if self.current_process:
                    try:
                        self.current_process.kill()
                    except Exception:
                        pass
        else:
            self.cancel_button["state"] = "disabled"

    def _execute_task_threaded(self, params):
        try:
            if params["mode"] == "convert":
                self.convert_file(params)
            else:
                self.compress_file(params)
        except Exception as e:
            traceback.print_exc()
            if not self.cancel_requested:
                self.task_queue.put(("error", str(e)))

    def _reset_ui_after_task(self, status_message, success=False):
        self.status_text.set(status_message)
        self.progressbar.stop()
        self.execute_button["state"] = "normal"
        self.cancel_button["state"] = "disabled"
        self.current_process = None
        self.cancel_requested = False
        if success:
            self.input_file_path.set("")
            self.file_info_text.set("ファイル未選択")
            self.info_label.config(foreground="gray")
            
    def process_queue(self):
        try:
            # キュー内のすべてのメッセージを処理するループ
            while True:
                message = self.task_queue.get_nowait()
                msg_type, msg_payload = message

                if msg_type == "status":
                    self.status_text.set(msg_payload)
                    
                elif msg_type == "ffmpeg_installed":
                    self.locate_binaries()
                    self.detect_encoders()
                    self.status_text.set("FFmpegのインストールが完了しました。")
                    self.execute_button["state"] = "normal"
                    messagebox.showinfo("完了", "FFmpegの準備が完了しました。")

                elif msg_type == "error":
                    self._reset_ui_after_task("エラーが発生しました", success=False)
                    messagebox.showerror("処理エラー", msg_payload)
                    
                elif msg_type == "success":
                    mode, msg = msg_payload
                    self._reset_ui_after_task(f"{mode}完了", success=True)
                    messagebox.showinfo("処理終了", msg)
                    
                elif msg_type == "cancelled":
                    self._reset_ui_after_task("処理が中断されました。", success=False)
                    messagebox.showwarning("中止", "処理がユーザーによって中断されました。")
                    
                elif msg_type == "warning":
                     messagebox.showwarning("警告", msg_payload)
        
        except Empty:
            pass
        
        self.after(100, self.process_queue)

    def convert_file(self, params):
        input_path = params["input_path"]
        target_ext = params["target_ext"]
        quality = params["quality"]
        selected_encoder_name = params.get("selected_encoder")
        
        encoder_codec = "libx264"
        for name, codec in self.available_encoders:
            if name == selected_encoder_name:
                encoder_codec = codec
                break
        
        if not target_ext:
            target_ext = input_path.split('.')[-1]
        
        # ピリオドが含まれていなければ付与
        if not target_ext.startswith('.'):
            target_ext = '.' + target_ext

        directory, filename = os.path.split(input_path)
        name_without_ext = os.path.splitext(filename)[0]
        output_path = os.path.join(directory, f"{name_without_ext}_converted{target_ext}")

        if os.path.abspath(input_path) == os.path.abspath(output_path):
             output_path = os.path.join(directory, f"{name_without_ext}_new{target_ext}")

        self.task_queue.put(("status", f"変換中({quality}, {encoder_codec})... -> {os.path.basename(output_path)}"))
        self._run_process(input_path, output_path, quality=quality, encoder=encoder_codec)
        
        if not self.cancel_requested:
            success_msg = f"ファイルの変換が完了しました。\n保存先: {output_path}"
            self.task_queue.put(("success", ("変換", success_msg)))
        else:
            self.task_queue.put(("cancelled", None))
            # キャンセル時は不完全なファイルを削除
            if os.path.exists(output_path):
                try: os.remove(output_path)
                except: pass

    def compress_file(self, params):
        try:
            target_size = float(params["target_size_mb"])
            if target_size <= 0: raise ValueError
        except ValueError:
            raise ValueError("目標ファイルサイズには正しい数値を入力してください。")

        selected_encoder_name = params.get("selected_encoder")
        encoder_codec = "libx264"
        for name, codec in self.available_encoders:
            if name == selected_encoder_name:
                encoder_codec = codec
                break
        
        input_path = params["input_path"]
        directory, filename = os.path.split(input_path)
        name, ext = os.path.splitext(filename)
        output_path = os.path.join(directory, f"{name}_compressed{ext}")
        
        if os.path.abspath(input_path) == os.path.abspath(output_path):
             output_path = os.path.join(directory, f"{name}_compressed_new{ext}")

        self.task_queue.put(("status", f"圧縮中... -> {os.path.basename(output_path)}"))
        
        self._run_process(input_path, output_path, target_size_mb=target_size, encoder=encoder_codec)

        if self.cancel_requested:
            self.task_queue.put(("cancelled", None))
            if os.path.exists(output_path):
                try: os.remove(output_path)
                except: pass
            return

        if os.path.exists(output_path):
            final_size_mb = os.path.getsize(output_path) / (1024 * 1024)
            msg = f"圧縮完了: {os.path.basename(output_path)} ({final_size_mb:.2f}MB)"
            self.task_queue.put(("status", msg))
            success_msg = f"ファイルの圧縮が完了しました。\n保存先: {output_path}\nサイズ: {final_size_mb:.2f}MB"
            self.task_queue.put(("success", ("圧縮", success_msg)))
        else:
            raise RuntimeError("出力ファイルが生成されませんでした。")

    def _run_process(self, input_path, output_path, quality=None, target_size_mb=None, encoder=None):
        input_ext = input_path.split('.')[-1].lower().replace('.', '')
        
        if input_ext in self.image_formats:
            self._process_image(input_path, output_path, quality, target_size_mb=target_size_mb)
        else:
            if not self.ffmpeg_path:
                raise RuntimeError("FFmpegが見つからないため、処理を実行できません。")
            self._process_video(input_path, output_path, quality, target_size_mb=target_size_mb, encoder=encoder)

    def _process_image(self, input_path, output_path, quality, target_size_mb=None):
        with Image.open(input_path) as img:
            output_ext = output_path.split('.')[-1].lower().replace('.', '')
            
            # アルファチャンネル処理
            if output_ext in ('jpg', 'jpeg') and img.mode in ('RGBA', 'LA', 'P'):
                if img.mode == 'P':
                    img = img.convert('RGB')
                else:
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[-1])
                    img = background

            if target_size_mb is not None:
                # 目標サイズ圧縮ロジック
                if output_ext not in ('jpg', 'jpeg', 'webp'):
                    self.task_queue.put(("warning", f"目標サイズ圧縮はJPG/WebPのみ対応しています。通常の変換を行います。"))
                    img.save(output_path)
                    return

                target_bytes = target_size_mb * 1024 * 1024
                low, high = 1, 100
                best_quality = 50 # デフォルト
                
                from io import BytesIO
                
                # フォーマット決定
                img_format = 'JPEG' if output_ext in ('jpg', 'jpeg') else 'WEBP'
                
                # 二分探索で最適な画質を探す
                while low <= high:
                    if self.cancel_requested: return
                    mid = (low + high) // 2
                    buffer = BytesIO()
                    img.save(buffer, format=img_format, quality=mid)
                    size = buffer.tell()
                    
                    if size <= target_bytes:
                        best_quality = mid
                        low = mid + 1
                    else:
                        high = mid - 1
                
                img.save(output_path, quality=best_quality)
                
                final_size = os.path.getsize(output_path)
                if final_size > target_bytes * 1.05: # 5%程度の誤差は許容
                     self.task_queue.put(("warning", f"最低画質でも目標サイズを超過しました ({final_size/(1024*1024):.2f}MB)。"))
                return

            # 通常画質設定
            options = {}
            if quality == "Original":
                if output_ext in ('jpg', 'jpeg'):
                    options['quality'] = 100
                    options['subsampling'] = 0
                elif output_ext == 'webp':
                    options['quality'] = 100
                    options['lossless'] = True
            elif output_ext in ('jpg', 'jpeg', 'webp'):
                q_val = {"High": 90, "Medium": 75, "Low": 50}.get(quality, 75)
                options['quality'] = q_val
            
            img.save(output_path, **options)

    def _run_ffmpeg_command(self, command, description="処理中"):
        """FFmpegコマンドを実行する共通メソッド"""
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        # ログ出力用（デバッグ時）
        # print(f"Running: {' '.join(command)}")

        self.current_process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
            text=True, encoding='utf-8', errors='replace', startupinfo=startupinfo
        )
        _, stderr = self.current_process.communicate()
        
        if self.current_process.returncode != 0:
            if not self.cancel_requested:
                # エラー解析とヒントの生成
                hint = ""
                if "Bitstream not supported" in stderr or "libaom-av1" in stderr:
                    hint = "\n【ヒント】入力ファイル(AV1等)がこのFFmpegバージョンでサポートされていないか、破損しています。"
                elif "Corrupt frame" in stderr:
                    hint = "\n【ヒント】ファイルの一部が破損しています。"
                
                # ログを短縮して表示
                lines = stderr.splitlines()
                log_tail = "\n".join(lines[-20:]) if len(lines) > 20 else stderr
                
                raise RuntimeError(f"FFmpegエラー ({description}):{hint}\n\n--- ログ末尾 ---\n{log_tail}")
        
        return stderr

    def _get_video_duration(self, input_path):
        if not self.ffprobe_path: raise RuntimeError("ffprobeが見つかりません。")
        
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
        command = [
            self.ffprobe_path, "-v", "error", "-show_entries",
            "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", input_path
        ]
        result = subprocess.run(
            command, check=False, capture_output=True, text=True, startupinfo=startupinfo
        )
        try:
            return float(result.stdout.strip())
        except ValueError:
            raise RuntimeError("動画の長さを取得できませんでした。")

    def _has_audio_stream(self, input_path):
        if not self.ffprobe_path: return False
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
        command = [
            self.ffprobe_path, "-v", "error", "-select_streams", "a",
            "-show_entries", "stream=index", "-of", "csv=p=0", input_path
        ]
        try:
            result = subprocess.run(
                command, check=False, capture_output=True, text=True, startupinfo=startupinfo
            )
            return bool(result.stdout.strip())
        except Exception:
            return False

    def _process_video(self, input_path, output_path, quality, target_size_mb=None, encoder=None):
        if self.cancel_requested: return
        
        has_audio = self._has_audio_stream(input_path)
        encoder = encoder or "libx264"

        # --- 目標サイズ指定（2パスエンコード） ---
        if target_size_mb is not None:
            try:
                duration = self._get_video_duration(input_path)
            except Exception as e:
                 raise RuntimeError(f"動画情報の取得失敗: {e}")

            # ビットレート計算 (kbits/s)
            # サイズ(MB) * 8192 (kbit/MB) / 秒数
            target_total_bitrate_kbps = (target_size_mb * 8192) / duration
            
            # 音声ビットレートの考慮
            audio_bitrate_kbps = 128 if has_audio else 0
            
            # 全体が小さすぎる場合は音声を削る
            if target_total_bitrate_kbps < audio_bitrate_kbps + 50: # 映像に最低50kbps残す
                 audio_bitrate_kbps = 64 # 音質を落とす
            
            target_video_bitrate_kbps = target_total_bitrate_kbps - audio_bitrate_kbps

            if target_video_bitrate_kbps < 100:
                self.task_queue.put(("warning", "目標サイズが極端に小さいため、画質が大幅に低下します。"))
                target_video_bitrate_kbps = max(30, target_video_bitrate_kbps) # 最低30kbps確保

            target_video_bitrate_str = f"{int(target_video_bitrate_kbps)}k"
            audio_bitrate_str = f"{audio_bitrate_kbps}k"
            
            with tempfile.TemporaryDirectory() as tempdir:
                # Windowsのパス区切り問題を回避するためにスラッシュ置換
                log_prefix = os.path.join(tempdir, "ffmpeg2pass").replace('\\', '/')
                null_device = "NUL" if os.name == 'nt' else "/dev/null"

                self.task_queue.put(("status", f"圧縮中... (1/2 パス, {encoder})"))
                
                # パス1コマンド（堅牢化フラグ追加）
                pass1_cmd = [
                    self.ffmpeg_path, "-y",
                    "-err_detect", "ignore_err", # 軽微なエラーを無視
                    "-i", input_path,
                    "-c:v", encoder, "-b:v", target_video_bitrate_str,
                    "-pass", "1", "-passlogfile", log_prefix,
                    "-an",
                    "-f", "mp4", null_device
                ]
                
                self._run_ffmpeg_command(pass1_cmd, description="Pass 1")
                
                if self.cancel_requested: return

                self.task_queue.put(("status", f"圧縮中... (2/2 パス, {encoder})"))

                pass2_cmd = [
                    self.ffmpeg_path,
                    "-err_detect", "ignore_err",
                    "-i", input_path,
                    "-c:v", encoder, "-b:v", target_video_bitrate_str,
                    "-pass", "2", "-passlogfile", log_prefix,
                ]

                if has_audio and audio_bitrate_kbps > 0:
                    pass2_cmd.extend(["-c:a", "aac", "-b:a", audio_bitrate_str])
                else:
                    pass2_cmd.append("-an")

                pass2_cmd.extend(["-y", output_path])
                
                self._run_ffmpeg_command(pass2_cmd, description="Pass 2")
            return

        # --- 通常変換モード ---
        output_ext = output_path.split('.')[-1].lower()
        need_reencode = True
        
        if quality == "Original":
             command = [
                self.ffmpeg_path, 
                "-err_detect", "ignore_err",
                "-i", input_path,
                "-c", "copy",
                "-y", output_path
            ]
             
             try:
                self._run_ffmpeg_command(command, description="Stream Copy")
                need_reencode = False
             except RuntimeError:
                 if self.cancel_requested: return
                 self.task_queue.put(("warning", "ストリームコピーに失敗しました。自動的に再エンコードします。"))
                 quality = "High"
                 need_reencode = True

        if not need_reencode:
            return
            
        supported_x264_containers = [
            "mp4", "mkv", "mov", "avi", "flv", "ts", "m2ts", "3gp", "wmv",
            "m4v", "mts", "f4v", "3g2"
        ]

        # 選択したエンコーダーが使えるコンテナかどうか判定
        if output_ext in supported_x264_containers:
            command = [
                self.ffmpeg_path,
                "-err_detect", "ignore_err", 
                "-i", input_path,
                "-c:v", encoder,
            ]
            
            if encoder == "libx264":
                crf_val = "23"
                if quality == "High": crf_val = "18"
                elif quality == "Low": crf_val = "28"
                command.extend(["-crf", crf_val, "-preset", "medium"])
                
            elif encoder == "h264_nvenc":
                cq_val = "23"
                if quality == "High": cq_val = "19"
                elif quality == "Low": cq_val = "28"
                command.extend(["-rc:v", "vbr_hq", "-cq:v", cq_val, "-b:v", "0"])
                
            elif encoder == "h264_qsv":
                q_val = "25"
                if quality == "High": q_val = "20"
                elif quality == "Low": q_val = "30"
                command.extend(["-global_quality", q_val])
            
            if has_audio:
                command.extend(["-c:a", "aac"])
            else:
                command.append("-an")

            command.extend(["-y", output_path])
            
        else:
            if quality != "Original":
                self.task_queue.put(("status", f"変換中... (形式 {output_ext} はHWエンコード未対応のため標準変換)"))

            command = [
                self.ffmpeg_path, 
                "-err_detect", "ignore_err",
                "-i", input_path,
                "-y", output_path
            ]
        
        self._run_ffmpeg_command(command, description="Encoding")

if __name__ == "__main__":
    app = ConverterApp()
    app.mainloop()