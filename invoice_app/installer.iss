; Windows版のインストーラー（setup.exe）を作る Inno Setup の設定（開発者専用。母上は使いません）。
;
; ふだんは GitHub Actions（.github/workflows/build-windows-exe.yml）が自動で使います。
; 手で作るときは、build_exe.bat で dist\invoice-generator-tool\ を作ったあと、
;     ISCC.exe /DAppVersion=1.9 installer.iss
; を実行すると、dist\invoice-generator-tool-windows-setup.exe ができます。
;
; ★大事なこと★
;   - AppId は絶対に変えないこと。変えると、更新のときに「別のアプリ」として
;     二重にインストールされてしまう。
;   - OutputBaseFilename（できるファイルの名前）は、アプリの自動更新（updater.py の
;     WINDOWS_INSTALLER_NAME）が名前で探しているので、変えるときは両方そろえること。
;   - 管理者の許可なしで入れられるように、パソコン全体ではなく
;     使っている人のフォルダ（%LOCALAPPDATA%\Programs\InvoiceGeneratorTool）に入れる。
;     こうしておくと、アプリの「🔄 アップデート確認」からの更新で
;     「このアプリがデバイスに変更を加えることを許可しますか？」が出ない。
;   - 振込先などの設定は %APPDATA%\InvoiceGeneratorTool\ にあり、
;     インストール・更新・アンインストールのどれでも消えない。

#define AppName "請求書かんたん作成ツール"
#define AppExeName "invoice-generator-tool.exe"
#ifndef AppVersion
  #error AppVersion を指定してください（例： ISCC.exe /DAppVersion=1.9 installer.iss）
#endif

[Setup]
AppId={{4401B9A2-2719-41E6-A1B3-F8C480714D8B}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} Version {#AppVersion}
AppPublisher=uhgm
AppPublisherURL=https://github.com/uhgm/InvoiceGen
AppSupportURL=https://github.com/uhgm/InvoiceGen
AppUpdatesURL=https://github.com/uhgm/InvoiceGen/releases/latest
VersionInfoVersion={#AppVersion}
; 使っている人のフォルダに入れる（管理者の許可が要らない）
PrivilegesRequired=lowest
DefaultDirName={autopf}\InvoiceGeneratorTool
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
DefaultGroupName={#AppName}
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=dist
OutputBaseFilename=invoice-generator-tool-windows-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ShowLanguageDialog=no
; 更新のとき、ツールが開いたままなら閉じてから上書きする。
; 開き直しは下の [Run] で行うので、Windowsの「再起動」機能は使わない（二重に開かないように）。
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; 前の版の部品（DLLなど）が残って混ざらないように、毎回まるごと入れ替える
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "dist\invoice-generator-tool\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
; ふつうにインストールしたとき：最後の画面に「起動する」のチェックを出す
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent runasoriginaluser
; アプリの「🔄 アップデート確認」から更新したとき（/SILENT）：終わったら自動で開き直す
Filename: "{app}\{#AppExeName}"; Flags: nowait skipifnotsilent runasoriginaluser
