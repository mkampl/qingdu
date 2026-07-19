<script setup lang="ts">
// Audit trust item — a plain, honest privacy page. Linked from the footer,
// the F-Droid listing, and the fastlane metadata. Content is written for
// the demo server (qingdu.itvoodoo.at); a self-hosted instance is governed
// by whoever runs it, and the page says so.
//
// Self-hosters can turn this page off entirely (PRIVACY_PAGE_ENABLED=false)
// if their jurisdiction doesn't require one or they'd rather link their own
// policy — the content below is written for the maintainer's demo server
// and would be misleading if left up unedited to describe someone else's.
import { onMounted } from "vue";

import { getApiBase, getDefaultApiBase } from "@/api/client";
import { useLegalStore } from "@/stores/legal";

const legal = useLegalStore();
onMounted(() => legal.load());

const serverShown =
  getApiBase() || getDefaultApiBase() || "the server you selected";
</script>

<template>
  <div
    v-if="legal.loaded && legal.config?.privacy_enabled === false"
    class="mx-auto max-w-2xl px-4 py-8 sm:px-6"
  >
    <header class="mb-8">
      <p class="font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle">
        轻读 QingDu
      </p>
      <h1 class="mt-1 font-display text-2xl font-medium tracking-tight text-fg">
        Privacy
      </h1>
    </header>
    <p class="text-sm text-fg-muted">
      This instance's operator hasn't published a privacy policy here.
    </p>
  </div>
  <div v-else class="mx-auto max-w-2xl px-4 py-8 sm:px-6">
    <header class="mb-8">
      <p class="font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle">
        轻读 QingDu
      </p>
      <h1 class="mt-1 font-display text-2xl font-medium tracking-tight text-fg">
        Privacy
      </h1>
      <p class="mt-2 text-sm text-fg-muted">
        Last updated 2026-07-19. Applies to the app and the maintainer's demo
        server. If you point the app at a self-hosted server, that server's
        operator — possibly you — controls the data instead, per the section
        below.
      </p>
    </header>

    <div class="space-y-8 text-sm leading-relaxed text-fg">
      <section>
        <h2 class="mb-2 font-display text-lg font-medium">
          Who's responsible for this data
        </h2>
        <template v-if="legal.config?.impressum">
          <p class="text-fg-muted">
            The data controller (<em>Verantwortlicher</em>, Art. 4(7) GDPR)
            for this server is:
          </p>
          <p class="mt-2 text-fg-muted">
            {{ legal.config.impressum.name }}<br />
            {{ legal.config.impressum.street }}<br />
            {{ legal.config.impressum.zip }} {{ legal.config.impressum.city
            }}<span v-if="legal.config.impressum.country"
              >, {{ legal.config.impressum.country }}</span
            ><br />
            <a
              :href="`mailto:${legal.config.impressum.email}`"
              class="text-accent underline-offset-2 hover:underline"
              >{{ legal.config.impressum.email }}</a
            >
          </p>
          <p class="mt-2 text-fg-muted">
            Full details, including anything the operator's own jurisdiction
            requires beyond this, on the
            <RouterLink
              to="/impressum"
              class="text-accent underline-offset-2 hover:underline"
              >Impressum</RouterLink
            >
            page.
          </p>
        </template>
        <p v-else class="text-fg-muted">
          This instance hasn't published operator contact details (see
          <RouterLink
            to="/impressum"
            class="text-accent underline-offset-2 hover:underline"
            >Impressum</RouterLink
          >). If you need to reach whoever runs it, check wherever you found
          this server.
        </p>
      </section>

      <section>
        <h2 class="mb-2 font-display text-lg font-medium">What's stored</h2>
        <p class="text-fg-muted">
          Your account is a username and a hashed password — no email, no
          phone number, no real name. Alongside it the server keeps what you
          create by using the app: saved texts, word states with their
          review schedule, vocabulary lists, review history, and settings.
          You can download all of it as one JSON file and delete the whole
          account yourself, both under Settings → Data &amp; account.
        </p>
      </section>

      <section>
        <h2 class="mb-2 font-display text-lg font-medium">What's not collected</h2>
        <p class="text-fg-muted">
          No analytics, no telemetry, no ads, no crash reporting, no
          third-party SDKs. The Android app talks to exactly one host: the
          server you chose at first launch ({{ serverShown }}). The one
          exception is the optional photo/scan import, which downloads its
          OCR engine from a public CDN the first time you use it.
        </p>
      </section>

      <section>
        <h2 class="mb-2 font-display text-lg font-medium">
          Legal basis for processing
        </h2>
        <ul class="list-disc space-y-1 pl-5 text-fg-muted">
          <li>
            Account data, saved texts, word states, and everything else you
            create by using the app — Art. 6(1)(b) GDPR, necessary to
            provide the service you signed up for.
          </li>
          <li>
            Sentence text sent to a translation provider and text sent to
            text-to-speech — also Art. 6(1)(b), necessary to carry out the
            specific feature you invoked.
          </li>
          <li>
            Signup-IP rate limiting and web-server logs — Art. 6(1)(f),
            legitimate interest in keeping the service available and
            abuse-free, limited to the short retention windows below.
          </li>
        </ul>
      </section>

      <section>
        <h2 class="mb-2 font-display text-lg font-medium">
          Third-party services the server uses
        </h2>
        <p class="text-fg-muted">
          When you tap a sentence to translate it, the demo server forwards
          that sentence to a translation provider — DeepL, Google Translate,
          or MyMemory, in that order of availability — and caches the
          result. Word and sentence audio is fetched from Google's public
          text-to-speech endpoint. Pronunciation recordings are decoded and
          scored in memory on the server and are not stored. If any of this
          is a concern, self-host: the server is the same open-source code,
          and translation keys are optional.
        </p>
        <p class="mt-2 text-fg-muted">
          Google Translate and Google's TTS endpoint are US-based and may
          process that text outside the EU/EEA under Google's standard
          contractual clauses; DeepL processes it in the EU. MyMemory's
          processing location isn't published by that provider. None of
          these providers get more than the sentence or word you asked to
          translate or hear — never your account identity.
        </p>
      </section>

      <section>
        <h2 class="mb-2 font-display text-lg font-medium">Demo-server housekeeping</h2>
        <ul class="list-disc space-y-1 pl-5 text-fg-muted">
          <li>
            Signup attempts keep the requesting IP address for up to 24
            hours, purely for rate limiting, then they're deleted.
          </li>
          <li>
            Ordinary web-server logs (IP address, requested path) exist
            briefly for operations and abuse handling.
          </li>
          <li>
            Accounts unused for 30 days are paused; paused accounts unused
            for 90 days are deleted along with all their data. Signing in
            again at any point before that reactivates the account. The app
            warns you in advance.
          </li>
        </ul>
      </section>

      <section>
        <h2 class="mb-2 font-display text-lg font-medium">Your rights</h2>
        <p class="text-fg-muted">
          Under Art. 15–21 GDPR you can request access to, correction of, or
          erasure of your data, ask that processing be restricted, receive
          your data in a portable format, and object to processing based on
          legitimate interest. Export and account deletion are self-service
          under Settings → Data &amp; account; for anything else, or if
          you'd rather not use the UI, reach the data controller named
          above.
        </p>
        <p class="mt-2 text-fg-muted">
          You can also lodge a complaint with a data protection supervisory
          authority. For the maintainer's demo server, operated from
          Austria, that's the
          <a
            href="https://www.dsb.gv.at"
            target="_blank"
            rel="noopener"
            class="text-accent underline-offset-2 hover:underline"
            >Datenschutzbehörde</a
          >; wherever you live, you can also use the authority in your own
          country of residence.
        </p>
      </section>

      <section>
        <h2 class="mb-2 font-display text-lg font-medium">Questions</h2>
        <p class="text-fg-muted">
          The entire stack is open source (MIT). Ask anything via
          <a
            href="https://github.com/mkampl/qingdu/issues"
            target="_blank"
            rel="noopener"
            class="text-accent underline-offset-2 hover:underline"
          >GitHub issues</a
          >.
        </p>
      </section>
    </div>
  </div>
</template>
