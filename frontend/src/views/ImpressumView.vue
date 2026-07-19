<script setup lang="ts">
// Content is entirely operator-supplied (env vars, see .env.example) — this
// component never hardcodes anyone's real name/address. If the operator
// hasn't configured it, that's a valid state for a self-hosted instance,
// not an error: show a neutral notice instead of a broken page.
import { onMounted } from "vue";

import { useLegalStore } from "@/stores/legal";

const legal = useLegalStore();
onMounted(() => legal.load());
</script>

<template>
  <div class="mx-auto max-w-2xl px-4 py-8 sm:px-6">
    <header class="mb-8">
      <p class="font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle">
        轻读 QingDu
      </p>
      <h1 class="mt-1 font-display text-2xl font-medium tracking-tight text-fg">
        Impressum
      </h1>
    </header>

    <div
      v-if="legal.config?.impressum"
      class="space-y-1 text-sm leading-relaxed text-fg"
    >
      <p class="font-medium">{{ legal.config.impressum.name }}</p>
      <p v-if="legal.config.impressum.street" class="text-fg-muted">
        {{ legal.config.impressum.street }}
      </p>
      <p class="text-fg-muted">
        <template v-if="legal.config.impressum.zip"
          >{{ legal.config.impressum.zip }}
        </template>{{ legal.config.impressum.city
        }}<template v-if="legal.config.impressum.country">
          , {{ legal.config.impressum.country }}
        </template>
      </p>
      <p class="pt-3">
        <a
          :href="`mailto:${legal.config.impressum.email}`"
          class="text-accent underline-offset-2 hover:underline"
          >{{ legal.config.impressum.email }}</a
        >
      </p>
      <p v-if="legal.config.impressum.phone" class="text-fg-muted">
        {{ legal.config.impressum.phone }}
      </p>
      <p
        v-if="legal.config.impressum.extra"
        class="whitespace-pre-line pt-3 text-fg-muted"
      >
        {{ legal.config.impressum.extra }}
      </p>
    </div>

    <p v-else-if="legal.loaded" class="text-sm text-fg-muted">
      This instance's operator hasn't published legal contact details here.
      If you need to reach them, check wherever you found this server (its
      website, app listing, or
      <a
        href="https://github.com/mkampl/qingdu"
        target="_blank"
        rel="noopener"
        class="text-accent underline-offset-2 hover:underline"
        >the project repository</a
      >
      if this is the maintainer's own demo instance).
    </p>
    <p v-else class="text-sm text-fg-subtle">Loading…</p>
  </div>
</template>
