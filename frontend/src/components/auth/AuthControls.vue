<script setup lang="ts">
import { onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";

import { useAuthStore } from "@/stores/auth";
import { useAuthModalsStore } from "@/stores/auth-modals";

import Button from "@/components/ui/Button.vue";
import ChangePasswordModal from "./ChangePasswordModal.vue";
import LoginModal from "./LoginModal.vue";
import SignupWithInviteModal from "./SignupWithInviteModal.vue";
import UserMenu from "./UserMenu.vue";

const auth = useAuthStore();
const modals = useAuthModalsStore();
const route = useRoute();
const router = useRouter();

// If the URL carries an invite token, auto-open the signup modal (mirrors the
// legacy app's ?invite= flow) and strip the param so reloading doesn't re-open
// the modal after the user has signed in.
onMounted(async () => {
  const token = route.query.invite;
  if (typeof token === "string" && token.length > 0 && !auth.isAuthed) {
    modals.openSignup(token);
    const cleaned = { ...route.query };
    delete cleaned.invite;
    await router.replace({ path: route.path, query: cleaned });
  }
});
</script>

<template>
  <div class="flex items-center gap-2">
    <UserMenu v-if="auth.isAuthed" />
    <Button
      v-else
      variant="secondary"
      size="sm"
      @click="modals.openLogin()"
    >
      Sign in
    </Button>

    <!-- Modals are mounted here regardless of auth state — the modal store
         decides which (if any) is open. Each modal Teleports to body. -->
    <LoginModal />
    <SignupWithInviteModal />
    <ChangePasswordModal />
  </div>
</template>
