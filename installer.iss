; Instalador do baixador-ytdlp (Inno Setup 6).
; Instala por usuário (sem UAC) e cria o atalho no Menu Iniciar,
; que é o que faz o app aparecer na busca do Windows.

#define AppName "baixador-ytdlp"
; A versão pode vir da linha de comando: ISCC /DAppVersion=1.2.3 installer.iss
#ifndef AppVersion
  #define AppVersion "1.5.2"
#endif
#define AppExe "baixador-ytdlp.exe"

[Setup]
AppId={{9C0B1F6E-9A1E-4C2E-9E7B-2D3A4F5B6C7D}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
OutputDir=dist\installer
OutputBaseFilename=BaixadorYtdlp-{#AppVersion}-setup
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
; O AppId é mantido desde a primeira versão: o Inno Setup encontra a instalação
; existente e atualiza a mesma pasta, sem criar um segundo programa no Windows.
UsePreviousAppDir=yes
CloseApplications=yes
CloseApplicationsFilter={#AppExe}
RestartApplications=no

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Files]
Source: "dist\{#AppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; A build one-dir do PyInstaller guarda as bibliotecas em _internal. Remover a
; cópia anterior evita DLLs e módulos órfãos após atualizar 1.0.x → 1.1.x.
[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos:"

[Run]
Filename: "{app}\{#AppExe}"; Description: "Abrir o {#AppName}"; Flags: nowait postinstall skipifsilent
