/* Local evidence fingerprint CLI; no network or external crypto library. */
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include "sha256.h"
static const char *signature(const unsigned char *b,size_t n){
if(n>=8&&memcmp(b,"\x89PNG\r\n\x1a\n",8)==0)return "PNG image";
if(n>=3&&b[0]==0xff&&b[1]==0xd8&&b[2]==0xff)return "JPEG image";
if(n>=4&&memcmp(b,"%PDF",4)==0)return "PDF document";
if(n>=4&&b[0]=='P'&&b[1]=='K'&&b[2]==3&&b[3]==4)return "ZIP container";
if(n>=2&&b[0]=='M'&&b[1]=='Z')return "Windows executable";
if(n>=4&&b[0]==0x7f&&memcmp(b+1,"ELF",3)==0)return "ELF executable";
return n==0?"Empty file":"Unknown / text / binary";
}
int main(int argc,char **argv){
FILE *f;unsigned char buf[65536],first[16],hash[32];size_t got,first_n=0,i;uint64_t size=0;npcip_sha256_ctx ctx;
if(argc!=2){fprintf(stderr,"Usage: npc-filehash <path>\n");return 2;}
f=fopen(argv[1],"rb");if(!f){perror("Cannot open file");return 1;}npcip_sha256_init(&ctx);
while((got=fread(buf,1,sizeof buf,f))>0){if(first_n<sizeof first){size_t take=got<sizeof first-first_n?got:sizeof first-first_n;memcpy(first+first_n,buf,take);first_n+=take;}size+=(uint64_t)got;npcip_sha256_update(&ctx,buf,got);}
if(ferror(f)){perror("Read failed");fclose(f);return 1;}fclose(f);npcip_sha256_final(&ctx,hash);
printf("file=%s\nsize_bytes=%llu\nkind=%s\nsha256=",argv[1],(unsigned long long)size,signature(first,first_n));
for(i=0;i<sizeof hash;i++)printf("%02x",hash[i]);printf("\nnotice=local-only; content was not uploaded or changed\n");return 0;
}
