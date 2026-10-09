gui:
  colorScheme: {{ mode }}
  theme:
    activeBorderColor:
      - "{{ accent }}"
      - bold
    inactiveBorderColor:
      - "{{ muted }}"
    searchingActiveBorderColor:
      - "{{ yellow }}"
      - bold
    optionsTextColor:
      - "{{ accent }}"
    selectedLineBgColor:
      - "{{ mix background accent 25% }}"
    inactiveViewSelectedLineBgColor:
      - "{{ mix background muted 35% }}"
    cherryPickedCommitFgColor:
      - "{{ accent }}"
    cherryPickedCommitBgColor:
      - "{{ mix background cyan 30% }}"
    markedBaseCommitFgColor:
      - "{{ accent }}"
    markedBaseCommitBgColor:
      - "{{ mix background yellow 30% }}"
    unstagedChangesColor:
      - "{{ red }}"
    defaultFgColor:
      - "{{ foreground }}"
    authorColors:
      "*": "{{ magenta }}"
