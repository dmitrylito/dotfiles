SPACESHIP_PROMPT_ORDER=(
  user
  host
  dir
  git            # Git section (git_branch + git_status)
  hg             # Mercurial section (hg_branch  + hg_status)
  package        # Package version
  node           # Node.js section
  bun            # Bun section
  deno           # Deno section
  ruby           # Ruby section
  python         # Python section
  elm            # Elm section
  elixir         # Elixir section
  xcode          # Xcode section
  xcenv          # xcenv section
  swift          # Swift section
  swiftenv       # swiftenv section
  golang         # Go section
  perl           # Perl section
  php            # PHP section
  rust           # Rust section
  haskell        # Haskell Stack section
  scala          # Scala section
  kotlin         # Kotlin section
  java           # Java section
  lua            # Lua section
  dart           # Dart section
  julia          # Julia section
  crystal        # Crystal section
  docker         # Docker section
  docker_compose # Docker section
  aws            # Amazon Web Services section
  # gcloud         # Google Cloud Platform section
  azure      # Azure section
  venv       # virtualenv section
  conda      # conda virtualenv section
  uv         # uv section
  dotnet     # .NET section
  ocaml      # OCaml section
  vlang      # V section
  zig        # Zig section
  purescript # PureScript section
  erlang     # Erlang section
  gleam      # Gleam section
  kubectl    # Kubectl context section
  ansible    # Ansible section
  terraform  # Terraform workspace section
  pulumi     # Pulumi stack section
  ibmcloud   # IBM Cloud section
  nix_shell  # Nix shell
  gnu_screen # GNU Screen section
  #exec_time      # Execution time
  #async          # Async jobs indicator
  #line_sep       # Line break
  battery   # Battery level and status
  jobs      # Background jobs indicator
  exit_code # Exit code section
  sudo      # Sudo indicator
  char
)

###########     Main      #########################
SPACESHIP_USER_SHOW=always
SPACESHIP_HOST_SHOW=always

SPACESHIP_PROMPT_ADD_NEWLINE=true

SPACESHIP_PROMPT_DEFAULT_SUFFIX=""

SPACESHIP_USER_SUFFIX=""
SPACESHIP_USER_COLOR=yellow

SPACESHIP_HOST_PREFIX="%{%F{red}%}@"
SPACESHIP_HOST_COLOR=green

SPACESHIP_DIR_PREFIX=" "

############     Git      #######################
SPACESHIP_GIT_SYMBOL=""
SPACESHIP_GIT_BRANCH_COLOR=magenta

SPACESHIP_DIR_TRUNC_REPO=false

SPACESHIP_GIT_PREFIX=" %{%F{magenta}%}| "

SPACESHIP_GIT_BRANCH_PREFIX=""
SPACESHIP_GIT_BRANCH_SUFFIX=""

SPACESHIP_GIT_COMMIT_SHOW=false

SPACESHIP_GIT_STATUS_PREFIX="["
SPACESHIP_GIT_STATUS_SUFFIX="]"

SPACESHIP_GIT_SUFFIX=""

#############   Docker    ########################
SPACESHIP_DOCKER_PREFIX="|"

##########    Main Prpompt Close   ###############
SPACESHIP_CHAR_PREFIX=" "
SPACESHIP_CHAR_SYMBOL=""
SPACESHIP_CHAR_SUFFIX=" "
SPACESHIP_CHAR_SYMBOL_SUCCESS=$SPACESHIP_CHAR_SYMBOL #Prompt character to be shown after successful command
SPACESHIP_CHAR_SYMBOL_FAILURE=$SPACESHIP_CHAR_SYMBOL
